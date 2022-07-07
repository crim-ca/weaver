"""
Stores to read/write data to from/to `MongoDB` using pymongo.
"""
import copy
import logging
import uuid
from typing import TYPE_CHECKING

import pymongo
from pymongo.collation import Collation
from pymongo.collection import ReturnDocument
from pymongo.errors import DuplicateKeyError
from pyramid.request import Request
from pywps import Process as ProcessWPS

from weaver.datatype import Bill, Job, Process, Quote, Service, VaultFile
from weaver.exceptions import (
    BillInstanceError,
    BillNotFound,
    BillRegistrationError,
    JobInvalidParameter,
    JobNotFound,
    JobRegistrationError,
    JobUpdateError,
    ListingInvalidParameter,
    ProcessInstanceError,
    ProcessNotAccessible,
    ProcessNotFound,
    ProcessRegistrationError,
    QuoteInstanceError,
    QuoteNotFound,
    QuoteRegistrationError,
    ServiceNotAccessible,
    ServiceNotFound,
    ServiceRegistrationError,
    VaultFileInstanceError,
    VaultFileNotFound,
    VaultFileRegistrationError
)
from weaver.execute import ExecuteMode
from weaver.formats import repr_json
from weaver.processes.types import ProcessType
from weaver.sort import Sort, SortMethods
from weaver.status import JOB_STATUS_CATEGORIES, Status, map_status
from weaver.store.base import StoreBills, StoreJobs, StoreProcesses, StoreQuotes, StoreServices, StoreVault
from weaver.utils import (
    VersionFormat,
    as_version_major_minor_patch,
    fully_qualified_name,
    get_base_url,
    get_sane_name,
    get_weaver_url,
    islambda,
    now
)
from weaver.visibility import Visibility
from weaver.wps.utils import get_wps_url

if TYPE_CHECKING:
    import datetime
    from typing import Any, Callable, Dict, List, Optional, Tuple, Union
    from pymongo.collection import Collection

    from weaver.execute import AnyExecuteResponse
    from weaver.processes.types import AnyProcessType
    from weaver.store.base import DatetimeIntervalType, JobGroupCategory, JobSearchResult
    from weaver.typedefs import (
        AnyProcess,
        AnyProcessClass,
        AnyUUID,
        AnyValueType,
        AnyVersion,
        ExecutionInputs,
        ExecutionOutputs
    )
    from weaver.visibility import AnyVisibility

    MongodbValue = Union[AnyValueType, datetime.datetime]
    MongodbAggregateExpression = Dict[str, Union[MongodbValue, List[MongodbValue], Dict[str, AnyValueType]]]
    MongodbAggregateStep = Union[MongodbValue, MongodbAggregateExpression]
    MongodbAggregatePipeline = List[Dict[str, Union[str, Dict[str, MongodbAggregateStep]]]]

LOGGER = logging.getLogger(__name__)


class MongodbStore(object):
    """
    Base class extended by all concrete store implementations.
    """

    def __init__(self, collection, sane_name_config=None):
        # type: (Collection, Optional[Dict[str, Any]]) -> None
        if not isinstance(collection, pymongo.collection.Collection):
            raise TypeError("Collection not of expected type.")
        self.collection = collection  # type: Collection
        self.sane_name_config = sane_name_config or {}

    @classmethod
    def get_args_kwargs(cls, *args, **kwargs):
        # type: (*Any, **Any) -> Tuple[Tuple, Dict]
        """
        Filters :class:`MongodbStore`-specific arguments to safely pass them down its ``__init__``.
        """
        collection = None
        if len(args):
            collection = args[0]
        elif "collection" in kwargs:    # pylint: disable=R1715
            collection = kwargs["collection"]
        sane_name_config = kwargs.get("sane_name_config", None)
        return tuple([collection]), {"sane_name_config": sane_name_config}


class MongodbServiceStore(StoreServices, MongodbStore):
    """
    Registry for OWS services.

    Uses `MongoDB` to store service url and attributes.
    """

    def __init__(self, *args, **kwargs):
        # type: (*Any, **Any) -> None
        db_args, db_kwargs = MongodbStore.get_args_kwargs(*args, **kwargs)
        StoreServices.__init__(self)
        MongodbStore.__init__(self, *db_args, **db_kwargs)

    def save_service(self, service, overwrite=True):
        # type: (Service, bool) -> Service
        """
        Stores an OWS service in mongodb.
        """
        service_url = get_base_url(service.url)
        # check if service is already registered
        if self.collection.count_documents({"url": service_url}) > 0:
            if overwrite:
                self.collection.delete_one({"url": service_url})
            else:
                raise ServiceRegistrationError("service url already registered.")
        service_name = get_sane_name(service.name, **self.sane_name_config)
        if self.collection.count_documents({"name": service_name}) > 0:
            if overwrite:
                self.collection.delete_one({"name": service_name})
            else:
                raise ServiceRegistrationError("service name already registered.")
        self.collection.insert_one(Service(
            url=service_url,
            name=service_name,
            type=service.type,
            public=service.public,
            auth=service.auth).params())
        return self.fetch_by_url(url=service_url)

    def delete_service(self, name):
        # type: (str) -> bool
        """
        Removes service from `MongoDB` storage.
        """
        self.collection.delete_one({"name": name})
        return True

    def list_services(self):
        # type: () -> List[Service]
        """
        Lists all services in `MongoDB` storage.
        """
        my_services = []
        for service in self.collection.find().sort("name", pymongo.ASCENDING):
            my_services.append(Service(service))
        return my_services

    def fetch_by_name(self, name, visibility=None):
        # type: (str, Optional[AnyVisibility]) -> Service
        """
        Gets service for given ``name`` from `MongoDB` storage.
        """
        service = self.collection.find_one({"name": name})
        if not service:
            raise ServiceNotFound(f"Service '{name}' could not be found.")
        service = Service(service)
        vis = Visibility.get(visibility)
        same_visibility = (
            (service.public and vis == Visibility.PUBLIC) or
            (not service.public and vis == Visibility.PRIVATE)
        )
        if visibility is not None and not same_visibility:
            raise ServiceNotAccessible(f"Service '{name}' cannot be accessed.")
        return service

    def fetch_by_url(self, url):
        # type: (str) -> Service
        """
        Gets service for given ``url`` from `MongoDB` storage.
        """
        service = self.collection.find_one({"url": get_base_url(url)})
        if not service:
            raise ServiceNotFound
        return Service(service)

    def clear_services(self):
        # type: () -> bool
        """
        Removes all OWS services from `MongoDB` storage.
        """
        self.collection.drop()
        return True


class ListingMixin(object):
    @staticmethod
    def _apply_paging_pipeline(page, limit):
        # type: (Optional[int], Optional[int]) -> List[MongodbAggregateStep]
        if isinstance(page, int) and isinstance(limit, int):
            return [{"$skip": page * limit}, {"$limit": limit}]
        if page is None and isinstance(limit, int):
            return [{"$limit": limit}]
        return []

    @staticmethod
    def _apply_sort_method(sort_field, sort_default, sort_allowed):
        # type: (Optional[str], str, List[str]) -> MongodbAggregateExpression
        sort = sort_field  # keep original sort field in case of error
        if sort is None:
            sort = sort_default
        elif sort == Sort.USER:
            sort = "user_id"
        if sort not in sort_allowed:
            raise ListingInvalidParameter(json={
                "description": "Invalid sorting method.",
                "cause": "sort",
                "value": str(sort_field),
            })
        sort_order = pymongo.DESCENDING if sort in (Sort.FINISHED, Sort.CREATED) else pymongo.ASCENDING
        return {sort: sort_order}

    @staticmethod
    def _apply_total_result(search_pipeline, extra_pipeline):
        # type: (MongodbAggregatePipeline, MongodbAggregatePipeline) -> MongodbAggregatePipeline
        """
        Extends the pipeline operations in order to obtain the grand total of matches in parallel to other filtering.

        A dual-branch search pipeline is created to apply distinct operations on each facet.
        The initial search are executed only once for both facets.
        The first obtains results with other processing steps specified, and the second calculates the total results.

        The result of the aggregation pipeline following this operation will be returned in the following format:

        .. code-block:: python

            [{
                "items": [ MatchedDocument, MatchedDocument, ... ],
                "total": int
            }]

        :param search_pipeline: pipeline employed to obtain initial matches against search filters.
        :param extra_pipeline: additional steps to generate specific results.
        :return: combination of the grand total of all items and their following processing representation.
        """
        total_pipeline = [
            {
                "$facet": {
                    "itemsPipeline": extra_pipeline,
                    "totalPipeline": [
                        {"$count": "total"}
                    ]
                },
            },
            {
                # reproject to avoid nested list of dicts (direct access)
                "$project": {
                    # if no items matched, 'items' is empty
                    # if items were matched, but then skipped over the last element due to paging 'skip'
                    # behaviour of 'arrayElemAt' index 0 causes out-of-bound which drops 'items'
                    # replace the removed 'items' by the empty list by default
                    "items": {
                        "$ifNull": [
                            "$itemsPipeline",  # if matched
                            []  # default
                        ],
                    },
                    # in the case of 'total', it is always present when any item is matched (whether skipped or not)
                    # but if none was matched, 'arrayElemAt' removes it
                    # set the default while it also gets moved it up for direct access
                    "total": {
                        "$ifNull": [
                            {"$arrayElemAt": ["$totalPipeline.total", 0]},  # if matched
                            0  # default
                        ]
                    }
                }
            }
        ]
        return search_pipeline + total_pipeline  # noqa


class MongodbProcessStore(StoreProcesses, MongodbStore, ListingMixin):
    """
    Registry for processes.

    Uses `MongoDB` to store processes and attributes.
    """

    def __init__(self, *args, **kwargs):
        # type: (*Any, **Any) -> None
        db_args, db_kwargs = MongodbStore.get_args_kwargs(*args, **kwargs)
        StoreProcesses.__init__(self)
        MongodbStore.__init__(self, *db_args, **db_kwargs)
        registry = kwargs.get("registry")
        default_processes = kwargs.get("default_processes")
        self.settings = kwargs.get("settings", {}) if not registry else registry.settings
        self.default_host = get_weaver_url(self.settings)
        self.default_wps_endpoint = get_wps_url(self.settings)

        # enforce default process re-registration to receive any applicable update
        if default_processes:
            self._register_defaults(default_processes)

    def _register_defaults(self, processes):
        # type: (List[Process]) -> None
        """
        Default process registration to apply definition updates with duplicate entry handling.
        """
        registered_processes = {process.identifier: process for process in self.list_processes()}
        for process in processes:
            process_id = self._get_process_id(process)
            registered = registered_processes.get(process_id)
            duplicate = False
            old_params = {}
            new_params = {}
            if registered:
                old_params = registered.params()
                new_params = process.params()
                duplicate = registered and old_params == new_params
            if registered and not duplicate:
                self.delete_process(process_id)
            # be more permissive of race-conditions between weaver api/worker booting
            # if the processes are complete duplicate, there is no reason to rewrite them
            try:
                if registered and not duplicate:
                    LOGGER.debug("Override non-duplicate matching process ID [%s]\n%s", process_id,
                                 [(param, old_params.get(param), new_params.get(param))
                                  for param in set(new_params) | set(old_params)])
                if not registered or not duplicate:
                    self._add_process(process, upsert=True)
            except DuplicateKeyError:
                if duplicate:
                    LOGGER.debug("Ignore verified duplicate default process definition [%s]", process_id)
                else:
                    raise

    def _add_process(self, process, upsert=False):
        # type: (AnyProcess, bool) -> None
        """
        Stores the specified process to the database.

        The operation assumes that any conflicting or duplicate process definition was pre-validated.
        Parameter ``upsert=True`` can be employed to allow exact replacement and ignoring duplicate errors.
        When using ``upsert=True``, it is assumed that whichever the result (insert, update, duplicate error)
        arises, the final result of the stored process should be identical in each case.

        .. note::
            Parameter ``upsert=True`` is useful for initialization-time of the storage with default processes that
            can sporadically generate clashing-inserts between multi-threaded/workers applications that all try adding
            builtin processes around the same moment.
        """
        new_process = Process.convert(process, processEndpointWPS1=self.default_wps_endpoint)
        if not isinstance(new_process, Process):
            raise ProcessInstanceError(f"Unsupported process type '{fully_qualified_name(process)}'")

        # apply defaults if not specified
        new_process["type"] = self._get_process_type(new_process)
        new_process["identifier"] = self._get_process_id(new_process)
        new_process["processEndpointWPS1"] = self._get_process_endpoint_wps1(new_process)
        new_process["visibility"] = new_process.visibility
        if upsert:
            search = {"identifier": new_process["identifier"]}
            try:
                result = self.collection.replace_one(search, new_process.params(), upsert=True)
                if result.matched_count != 0 and result.modified_count != 0:
                    LOGGER.warning(
                        "Duplicate key in collection: %s index: %s "
                        "was detected during replace with upsert, but permitted for process without modification.",
                        self.collection.full_name, search
                    )
            except DuplicateKeyError:
                LOGGER.warning(
                    "Duplicate key in collection: %s index: %s "
                    "was detected during internal insert retry, but ignored for process without modification.",
                    self.collection.full_name, search
                )
        else:
            self.collection.insert_one(new_process.params())

    @staticmethod
    def _get_process_field(process, function_dict):
        # type: (AnyProcess, Union[Dict[AnyProcessClass, Callable[[], Any]], Callable[[], Any]]) -> Any
        """
        Obtain a field from a process instance after validation and using mapping of process implementation functions.

        Takes a lambda expression or a dict of process-specific lambda expressions to retrieve a field.
        Validates that the passed process object is one of the supported types.

        :param process: process to retrieve the field from.
        :param function_dict: lambda or dict of lambda of process type.
        :return: retrieved field if the type was supported.
        :raises ProcessInstanceError: invalid process type.
        """
        if isinstance(process, Process):
            if islambda(function_dict):
                return function_dict()
            return function_dict[Process]()
        elif isinstance(process, ProcessWPS):
            if islambda(function_dict):
                return function_dict()
            return function_dict[ProcessWPS]()
        else:
            raise ProcessInstanceError(f"Unsupported process type '{fully_qualified_name(process)}'")

    def _get_process_id(self, process):
        # type: (AnyProcess) -> str
        return self._get_process_field(process, lambda: process.identifier)

    def _get_process_type(self, process):
        # type: (AnyProcess) -> AnyProcessType
        return self._get_process_field(process, {
            Process: lambda: process.type,
            ProcessWPS: lambda: getattr(process, "type", ProcessType.WPS_LOCAL)
        }).lower()

    def _get_process_endpoint_wps1(self, process):
        # type: (AnyProcess) -> str
        url = self._get_process_field(process, {Process: lambda: process.processEndpointWPS1,
                                                ProcessWPS: lambda: None})
        if not url:
            url = self.default_wps_endpoint
        return url

    def save_process(self, process, overwrite=True):
        # type: (Union[Process, ProcessWPS], bool) -> Process
        """
        Stores a process in storage.

        :param process: An instance of :class:`weaver.datatype.Process`.
        :param overwrite: Overwrite the matching process instance by name if conflicting.
        """
        process_id = self._get_process_id(process)
        sane_name = get_sane_name(process_id, **self.sane_name_config)
        if self.collection.count_documents({"identifier": sane_name}) > 0:
            if overwrite:
                self.collection.delete_one({"identifier": sane_name})
            else:
                raise ProcessRegistrationError(f"Process '{sane_name}' already registered.")
        process.identifier = sane_name  # must use property getter/setter to match both 'Process' types
        self._add_process(process)
        return self.fetch_by_id(sane_name)

    def delete_process(self, process_id, visibility=None):
        # type: (str, Optional[Visibility]) -> bool
        """
        Removes process from database, optionally filtered by visibility.

        If ``visibility=None``, the process is deleted (if existing) regardless of its visibility value.
        """
        process = self.fetch_by_id(process_id, visibility=visibility)  # ensure accessible before delete
        if not process:
            raise ProcessNotFound(f"Process '{process_id}' could not be found.")
        revisions = self.find_versions(process_id, VersionFormat.STRING)
        search, _ = self._get_revision_search(process_id)
        status = bool(self.collection.delete_one(search).deleted_count)
        if not status or not len(revisions) > 1 or not process.version:
            return status
        # if process was the latest revision, fallback to previous one as new latest
        version = as_version_major_minor_patch(process.version, VersionFormat.STRING)
        if version == revisions[-1]:
            latest = revisions[-2]  # prior version
            proc_latest = f"{process_id}:{latest}"
            self.revert_latest(proc_latest)
        return status

    def list_processes(self,
                       visibility=None,     # type: Optional[AnyVisibility, List[AnyVisibility]]
                       page=None,           # type: Optional[int]
                       limit=None,          # type: Optional[int]
                       sort=None,           # type: Optional[str]
                       total=False,         # type: bool
                       revisions=False,     # type: bool
                       process=None,        # type: Optional[str]
                       ):                   # type: (...) -> Union[List[Process], Tuple[List[Process], int]]
        """
        Lists all processes in database, optionally filtered by `visibility`.

        :param visibility: One or many value amongst :class:`Visibility`.
        :param page: Page number to return when using result paging.
        :param limit: Number of processes per page when using result paging.
        :param sort: Field which is used for sorting results (default: process ID, descending).
        :param total: Request the total number of processes to be calculated (ignoring paging).
        :param revisions: Include all process revisions instead of only latest ones.
        :param process: Limit results only to specified process ID (makes sense mostly when combined with revisions).
        :returns:
            List of sorted, and possibly page-filtered, processes matching queries.
            If ``total`` was requested, return a tuple of this list and the number of processes.
        """
        search_filters = {}  # type: MongodbAggregateExpression

        if process and revisions:
            search_filters["identifier"] = {"$regex": rf"^{process}(:.*)?$"}  # revisions of that process
        elif process and not revisions:
            search_filters["identifier"] = process  # not very relevant 'listing', but valid (explicit ID)
        elif not process and not revisions:
            search_filters["identifier"] = {"$regex": r"^[\w\-]+$"}  # exclude ':' to keep only latest (default)
        # otherwise, last case returns 'everything', so nothing to 'filter'

        if visibility is None:
            visibility = Visibility.values()
        if not isinstance(visibility, list):
            visibility = [visibility]
        for v in visibility:
            vis = Visibility.get(v)
            if vis not in Visibility:
                raise ValueError(f"Invalid visibility value '{v!s}' is not one of {list(Visibility.values())!s}")
        search_filters["visibility"] = {"$in": list(visibility)}
        insert_fields = []  # type: MongodbAggregatePipeline

        # processes do not have 'created', but ObjectID in '_id' has the particularity of embedding creation time
        if sort == Sort.CREATED:
            sort = "_id"
        # replace equivalent aliases to corresponding fields in db
        if sort in [Sort.ID, Sort.PROCESS]:
            sort = Sort.ID_LONG
        sort_allowed = list(SortMethods.PROCESS) + ["_id"]
        sort_fields = self._apply_sort_method(sort, Sort.ID_LONG, sort_allowed)
        if revisions and sort in [Sort.ID, Sort.ID_LONG, Sort.PROCESS]:
            # If listing many revisions, sort by version on top of ID to make listing more natural.
            # Because the "latest version" is saved with 'id' only while "older revisions" are saved with 'id:version',
            # that more recent version would always appear first since alphabetical sort: 'id' (latest) < 'id:version'.
            # Work around this by dynamically reassigning 'id' by itself.
            insert_fields = [
                {"$set": {"tag": {"$cond": {
                    "if": {"identifier": "/^.*:.*$/"},
                    "then": "$identifier",
                    "else": {"$concat": ["$identifier", ":", "$version"]},
                }}}},
                {"$set": {"id_version": {"$split": ["$tag", ":"]}}},
                {"$set": {"identifier": {"$arrayElemAt": ["$id_version", 0]}}},
            ]
            sort_fields = {"identifier": pymongo.ASCENDING, "version": pymongo.ASCENDING}
        sort_method = [{"$sort": sort_fields}]

        search_pipeline = insert_fields + [{"$match": search_filters}] + sort_method
        paging_pipeline = self._apply_paging_pipeline(page, limit)
        if total:
            pipeline = self._apply_total_result(search_pipeline, paging_pipeline)
        else:
            pipeline = search_pipeline + paging_pipeline
        LOGGER.debug("Process listing pipeline:\n%s", repr_json(pipeline, indent=2))

        found = list(self.collection.aggregate(pipeline, collation=Collation(locale="en")))
        if total:
            items = [Process(item) for item in found[0]["items"]]
            total = found[0]["total"]
            return items, total
        return [Process(item) for item in found]

    def _get_revision_search(self, process_id):
        # type: (str) -> Tuple[MongodbAggregateExpression, Optional[str]]
        """
        Obtain the search criteria and version of the specified :term:`Process` ID if it specified a revision tag.

        :return: Database search operation and the matched version as string.
        """
        version = None
        if ":" in process_id:
            process_id, version = Process.split_version(process_id)
        sane_name = get_sane_name(process_id, **self.sane_name_config)
        search = {"identifier": sane_name}
        if version:
            version = as_version_major_minor_patch(version, VersionFormat.STRING)  # make sure it is padded
            sane_tag = sane_name + ":" + version
            search = {"$or": [{"identifier": sane_tag}, {"identifier": sane_name, "version": version}]}
        return search, version

    def fetch_by_id(self, process_id, visibility=None):
        # type: (str, Optional[AnyVisibility]) -> Process
        """
        Get process for given :paramref:`process_id` from storage, optionally filtered by :paramref:`visibility`.

        If ``visibility=None``, the process is retrieved (if existing) regardless of its visibility value.

        :param process_id: Process identifier (optionally with version tag).
        :param visibility: One value amongst :py:mod:`weaver.visibility`.
        :return: An instance of :class:`weaver.datatype.Process`.
        """
        search, version = self._get_revision_search(process_id)
        process = self.collection.find_one(search)
        if not process:
            raise ProcessNotFound(f"Process '{process_id}' could not be found.")
        process = Process(process)
        if version:
            process.version = version  # ensure version was applied just in case
        if visibility is not None and process.visibility != visibility:
            raise ProcessNotAccessible(f"Process '{process_id}' cannot be accessed.")
        return process

    def find_versions(self, process_id, version_format=VersionFormat.OBJECT):
        # type: (str, VersionFormat) -> List[AnyVersion]
        """
        Retrieves all existing versions of a given process.
        """
        process_id = Process.split_version(process_id)[0]  # version never needed to fetch all revisions
        sane_name = get_sane_name(process_id, **self.sane_name_config)
        version_name = rf"^{sane_name}(:[0-9]+\.[0-9]+.[0-9]+)?$"
        versions = self.collection.find(
            filter={"identifier": {"$regex": version_name}},
            projection={"_id": False, "version": True},
            sort=[(Sort.VERSION, pymongo.ASCENDING)],
        )
        return [as_version_major_minor_patch(ver["version"], version_format) for ver in versions]

    def update_version(self, process_id, version):
        # type: (str, AnyVersion) -> Process
        """
        Updates the specified (latest) process ID to become an older revision.

        .. seealso::
            Use :meth:`revert_latest` for the inverse operation.

        :returns: Updated process definition with older revision.
        """
        sane_name = get_sane_name(process_id, **self.sane_name_config)
        version = as_version_major_minor_patch(version, VersionFormat.STRING)
        # update ID to allow direct fetch by ID using tagged version
        # this also clears the unique ID index requirement
        new_name = sane_name + ":" + version
        process = self.collection.find_one_and_update(
            filter={"identifier": sane_name},
            update={"$set": {"identifier": new_name, "version": version}},
            return_document=ReturnDocument.AFTER,
        )
        if not process:
            raise ProcessNotFound(f"Process '{sane_name}' could not be found for version update.")
        process = Process(process)
        return process

    def revert_latest(self, process_id):
        # type: (str) -> Process
        """
        Makes the specified (older) revision process the new latest revision.

        Assumes there are no active *latest* in storage. If one is still defined, it will generate a conflict.
        The process ID must also contain a tagged revision. Failing to provide a version will fail the operation.

        .. seealso::
            Use :meth:`update_version` for the inverse operation.

        :returns: Updated process definition with older revision.
        """
        search, version = self._get_revision_search(process_id)
        if not version:
            raise ProcessNotFound(f"Process '{process_id}' missing version part to revert as latest.")
        p_name = Process.split_version(process_id)[0]
        process = self.collection.find_one_and_update(
            filter=search,
            update={"$set": {"identifier": p_name, "version": version}},
            return_document=ReturnDocument.AFTER,
        )
        if not process:
            raise ProcessNotFound(f"Process '{process_id}' could not be found for revert as latest.")
        process = Process(process)
        return process

    def get_visibility(self, process_id):
        # type: (str) -> Visibility
        """
        Get `visibility` of a process.

        :returns: One value amongst `weaver.visibility`.
        """
        process = self.fetch_by_id(process_id)
        return process.visibility

    def set_visibility(self, process_id, visibility):
        # type: (str, AnyVisibility) -> None
        """
        Set `visibility` of a process.

        :param visibility: One value amongst `weaver.visibility`.
        :param process_id:
        :raises TypeError: when :paramref:`visibility` is not :class:`str`.
        :raises ValueError: when :paramref:`visibility` is not one of :class:`Visibility`.
        """
        process = self.fetch_by_id(process_id)
        process.visibility = visibility
        self.save_process(process, overwrite=True)

    def clear_processes(self):
        # type: () -> bool
        """
        Clears all processes from the store.
        """
        self.collection.drop()
        return True


class MongodbJobStore(StoreJobs, MongodbStore, ListingMixin):
    """
    Registry for process jobs tracking.

    Uses `MongoDB` to store job attributes.
    """

    def __init__(self, *args, **kwargs):
        # type: (*Any, **Any) -> None
        db_args, db_kwargs = MongodbStore.get_args_kwargs(*args, **kwargs)
        StoreJobs.__init__(self)
        MongodbStore.__init__(self, *db_args, **db_kwargs)

    def save_job(self,
                 task_id,                   # type: AnyUUID
                 process,                   # type: str
                 service=None,              # type: Optional[str]
                 inputs=None,               # type: Optional[ExecutionInputs]
                 outputs=None,              # type: Optional[ExecutionOutputs]
                 is_workflow=False,         # type: bool
                 is_local=False,            # type: bool
                 execute_async=True,        # type: bool
                 execute_response=None,     # type: Optional[AnyExecuteResponse]
                 custom_tags=None,          # type: Optional[List[str]]
                 user_id=None,              # type: Optional[int]
                 access=None,               # type: Optional[AnyVisibility]
                 context=None,              # type: Optional[str]
                 notification_email=None,   # type: Optional[str]
                 accept_language=None,      # type: Optional[str]
                 created=None,              # type: Optional[datetime.datetime]
                 ):                         # type: (...) -> Job
        """
        Creates a new :class:`Job` and stores it in mongodb.
        """
        try:
            tags = ["dev"]
            tags.extend(list(filter(lambda t: bool(t), custom_tags or [])))  # remove empty tags
            if is_workflow:
                tags.append(ProcessType.WORKFLOW)
            else:
                tags.append(ProcessType.APPLICATION)
            if execute_async:
                tags.append(ExecuteMode.ASYNC)
            else:
                tags.append(ExecuteMode.SYNC)
            if not access:
                access = Visibility.PRIVATE

            new_job = Job({
                "task_id": task_id,
                "user_id": user_id,
                "service": service,     # provider identifier (WPS service)
                "process": process,     # process identifier (WPS request)
                "inputs": inputs,
                "outputs": outputs,
                "status": map_status(Status.ACCEPTED),
                "execute_async": execute_async,
                "execution_response": execute_response,
                "is_workflow": is_workflow,
                "is_local": is_local,
                "created": created if created else now(),
                "updated": now(),
                "tags": list(set(tags)),  # remove duplicates
                "access": access,
                "context": context,
                "notification_email": notification_email,
                "accept_language": accept_language,
            })
            self.collection.insert_one(new_job.params())
            job = self.fetch_by_id(job_id=new_job.id)
        except Exception as ex:
            raise JobRegistrationError(f"Error occurred during job registration: [{ex!r}]")
        if job is None:
            raise JobRegistrationError("Failed to retrieve registered job.")
        return job

    def batch_update_jobs(self, job_filter, job_update):
        # type: (Dict[str, Any], Dict[str, Any]) -> int
        """
        Update specified fields of matched jobs against filters.

        :param job_update: Fields and values to update on matched jobs.
        :param job_filter: Fields to filter jobs to be updated.
        :return: Number of affected jobs.
        """
        filter_keys = list(Job.properties())
        job_update = copy.deepcopy(job_update)
        for job_key in list(job_update):
            if job_key not in filter_keys:
                job_update.pop(job_key)
        job_filter = copy.deepcopy(job_filter)
        for job_key in list(job_filter):
            if job_key not in filter_keys:
                job_filter.pop(job_key)
        if not job_update:
            raise JobUpdateError("No job parameters specified to apply update.")
        job_update = {"$set": job_update}
        LOGGER.debug("Batch jobs update:\nfilter:\n%s\nupdate:\n%s",
                     repr_json(job_filter, indent=2), repr_json(job_update, indent=2))
        result = self.collection.update_many(filter=job_filter, update=job_update)
        return result.modified_count

    def update_job(self, job):
        # type: (Job) -> Job
        """
        Updates a job parameters in `MongoDB` storage.

        :param job: instance of ``weaver.datatype.Job``.
        """
        try:
            job.updated = now()
            result = self.collection.update_one({"id": job.id}, {"$set": job.params()})
            if result.acknowledged and result.matched_count == 1:
                return self.fetch_by_id(job.id)
        except Exception as ex:
            raise JobUpdateError(f"Error occurred during job update: [{ex!r}]")
        raise JobUpdateError(f"Failed to update specified job: '{job!s}'")

    def delete_job(self, job_id):
        # type: (AnyUUID) -> bool
        """
        Removes job from `MongoDB` storage.
        """
        if isinstance(job_id, str):
            job_id = uuid.UUID(job_id)
        result = self.collection.delete_one({"id": job_id})
        return result.deleted_count == 1

    def fetch_by_id(self, job_id):
        # type: (AnyUUID) -> Job
        """
        Gets job for given ``job_id`` from `MongoDB` storage.
        """
        if isinstance(job_id, str):
            job_id = uuid.UUID(job_id)
        job = self.collection.find_one({"id": job_id})
        if not job:
            raise JobNotFound(f"Could not find job matching: '{job_id}'")
        return Job(job)

    def list_jobs(self):
        # type: () -> List[Job]
        """
        Lists all jobs in `MongoDB` storage.

        For user-specific access to available jobs, use :meth:`MongodbJobStore.find_jobs` instead.
        """
        jobs = []
        for job in self.collection.find().sort(Sort.ID, pymongo.ASCENDING):
            jobs.append(Job(job))
        return jobs

    def find_jobs(self,
                  process=None,             # type: Optional[str]
                  service=None,             # type: Optional[str]
                  job_type=None,            # type: Optional[str]
                  tags=None,                # type: Optional[List[str]]
                  access=None,              # type: Optional[str]
                  notification_email=None,  # type: Optional[str]
                  status=None,              # type: Optional[str]
                  sort=None,                # type: Optional[str]
                  page=0,                   # type: Optional[int]
                  limit=10,                 # type: Optional[int]
                  min_duration=None,        # type: Optional[int]
                  max_duration=None,        # type: Optional[int]
                  datetime_interval=None,   # type: Optional[DatetimeIntervalType]
                  group_by=None,            # type: Optional[Union[str, List[str]]]
                  request=None,             # type: Optional[Request]
                  ):                        # type: (...) -> JobSearchResult
        """
        Finds all jobs in `MongoDB` storage matching search filters to obtain results with requested paging or grouping.

        Using paging (default), result will be in the form.

        .. code-block:: python

            (
                [Job(1), Job(2), Job(3), ...],
                <total>
            )

        Where ``<total>`` will indicate the complete count of matched jobs with filters, but the list of jobs
        will be limited only to ``page`` index and ``limit`` specified.

        Limit and paging can be disabled by setting them to ``None``.
        Paging must always be combined with limit, but limit can be employed by itself.

        Using grouping with a list of field specified with ``group_by``, results will be in the form.

        .. code-block:: python

            (
                [{category: {field1: valueA, field2: valueB, ...}, [Job(1), Job(2), ...], count: <count>},
                 {category: {field1: valueC, field2: valueD, ...}, [Job(x), Job(y), ...], count: <count>},
                 ...
                ],
                <total>
            )

        Where ``<total>`` will again indicate all matched jobs by every category combined, and ``<count>`` will
        indicate the amount of jobs matched for each individual category. Also, ``category`` will indicate values
        of specified fields (from ``group_by``) that compose corresponding jobs with matching values.

        :param request: request that lead to this call to obtain permissions and user id.
        :param process: process name to filter matching jobs.
        :param service: service name to filter matching jobs.
        :param job_type: filter matching jobs for given type.
        :param tags: list of tags to filter matching jobs.
        :param access: access visibility to filter matching jobs (default: :py:data:`Visibility.PUBLIC`).
        :param notification_email: notification email to filter matching jobs.
        :param status: status to filter matching jobs.
        :param sort: field which is used for sorting results (default: creation date, descending).
        :param page: page number to return when using result paging (only when not using ``group_by``).
        :param limit: number of jobs (per page or total) when using result paging (only when not using ``group_by``).
        :param min_duration: minimal duration (seconds) between started time and current/finished time of jobs to find.
        :param max_duration: maximum duration (seconds) between started time and current/finished time of jobs to find.
        :param datetime_interval: field used for filtering data by creation date with a given date or interval of date.
        :param group_by: one or many fields specifying categories to form matching groups of jobs (paging disabled).
        :returns: (list of jobs matching paging OR list of {categories, list of jobs, count}) AND total of matched job.
        """
        search_filters = {}
        if notification_email is not None:
            search_filters["notification_email"] = notification_email

        search_filters.update(self._apply_status_filter(status))
        search_filters.update(self._apply_ref_or_type_filter(job_type, process, service))
        search_filters.update(self._apply_access_filter(access, request))
        search_filters.update(self._apply_datetime_filter(datetime_interval))

        # minimal operation, only search for matches and sort them
        pipeline = [{"$match": search_filters}]  # expected for all filters except 'duration'
        self._apply_duration_filter(pipeline, min_duration, max_duration)

        sort_method = {"$sort": self._apply_sort_method(sort, Sort.CREATED, SortMethods.JOB)}
        pipeline.append(sort_method)

        # results by group categories or with job list paging
        if group_by:
            results = self._find_jobs_grouped(pipeline, group_by)
        else:
            results = self._find_jobs_paging(pipeline, page, limit)
        return results

    def _find_jobs_grouped(self, pipeline, group_categories):
        # type: (MongodbAggregatePipeline, List[str]) -> Tuple[JobGroupCategory, int]
        """
        Retrieves jobs regrouped by specified field categories and predefined search pipeline filters.
        """
        groups = [group_categories] if isinstance(group_categories, str) else group_categories
        has_provider = "provider" in groups
        if has_provider:
            groups.remove("provider")
            groups.append("service")
        group_categories = {field: "$" + field for field in groups}  # fields that can generate groups
        group_pipeline = [{
            "$group": {
                "_id": group_categories,        # grouping categories to aggregate corresponding jobs
                "jobs": {"$push": "$$ROOT"},    # matched jobs for corresponding grouping categories
                "count": {"$sum": 1}},          # count of matches for corresponding grouping categories
            }, {                        # noqa: E123  # ignore indentation checks
            "$project": {
                "_id": False,           # removes "_id" field from results
                "category": "$_id",     # renames "_id" grouping categories key
                "jobs": "$jobs",        # preserve field
                "count": "$count",      # preserve field
            }
        }]
        pipeline = self._apply_total_result(pipeline, group_pipeline)
        LOGGER.debug("Job search pipeline:\n%s", repr_json(pipeline, indent=2))

        found = list(self.collection.aggregate(pipeline, collation=Collation(locale="en")))
        items = found[0]["items"]
        # convert to Job object where applicable, since pipeline result contains (category, jobs, count)
        items = [{k: (v if k != "jobs" else [Job(j) for j in v]) for k, v in i.items()} for i in items]
        if has_provider:
            for group_result in items:
                group_service = group_result["category"].pop("service", None)
                group_result["category"]["provider"] = group_service
        total = found[0]["total"] if items else 0
        return items, total

    def _find_jobs_paging(self, search_pipeline, page, limit):
        # type: (MongodbAggregatePipeline, Optional[int], Optional[int]) -> Tuple[List[Job], int]
        """
        Retrieves jobs limited by specified paging parameters and predefined search pipeline filters.
        """
        paging_pipeline = self._apply_paging_pipeline(page, limit)
        pipeline = self._apply_total_result(search_pipeline, paging_pipeline)
        LOGGER.debug("Job search pipeline:\n%s", repr_json(pipeline, indent=2))

        found = list(self.collection.aggregate(pipeline))
        items = [Job(item) for item in found[0]["items"]]
        total = found[0]["total"]
        return items, total

    @staticmethod
    def _apply_tags_filter(tags):
        bad_tags = [vis for vis in Visibility.values() if vis in tags]
        if any(bad_tags):
            raise JobInvalidParameter(json={
                "code": "JobInvalidParameter",
                "description": "Visibility values not acceptable in 'tags', use 'access' instead.",
                "cause": f"Invalid value{'s'[:len(bad_tags)^1]} in 'tags': {','.join(bad_tags)}",
                "locator": "tags",
            })
        if tags:
            return {"tags": {"$all": tags}}
        return {}

    @staticmethod
    def _apply_access_filter(access, request):
        # type: (AnyVisibility, Request) -> MongodbAggregateExpression
        search_filters = {}
        if not request:
            search_filters["access"] = Visibility.PUBLIC
        else:
            if request.authenticated_userid is not None and request.has_permission("admin"):
                vis = Visibility.get(access)
                if vis:
                    search_filters["access"] = vis
            else:
                user_id = request.authenticated_userid
                if user_id is not None:
                    search_filters["user_id"] = user_id
                    vis = Visibility.get(access)
                    if vis:
                        search_filters["access"] = vis
                else:
                    search_filters["access"] = Visibility.PUBLIC
        return search_filters

    @staticmethod
    def _apply_ref_or_type_filter(job_type, process, service):
        # type: (Optional[str], Optional[str], Optional[str]) -> MongodbAggregateExpression

        search_filters = {}  # type: MongodbAggregateExpression
        if job_type == "process":
            search_filters["service"] = None
        elif job_type == "provider":
            search_filters["service"] = {"$ne": None}

        if process is not None:
            # if (type=provider and process=<id>)
            # doesn't contradict since it can be more specific about sub-process of service
            search_filters["process"] = process

        if service is not None:
            # can override 'service' set by 'type' to be more specific, but must be logical
            # (e.g.: type=process and service=<name> cannot ever yield anything)
            if search_filters.get("service", -1) is None:
                raise JobInvalidParameter(json={
                    "code": "JobInvalidParameter",
                    "description": "Ambiguous job type requested contradicts with requested service provider.",
                    "value": {"service": service, "type": job_type}
                })
            search_filters["service"] = service

        return search_filters

    @staticmethod
    def _apply_status_filter(status):
        # type: (Optional[str]) -> MongodbAggregateExpression
        search_filters = {}  # type: MongodbAggregateExpression
        if status in JOB_STATUS_CATEGORIES:
            category_statuses = list(JOB_STATUS_CATEGORIES[status])
            search_filters["status"] = {"$in": category_statuses}
        elif status:
            search_filters["status"] = status
        return search_filters

    @staticmethod
    def _apply_datetime_filter(datetime_interval):
        # type: (Optional[DatetimeIntervalType]) -> MongodbAggregateExpression
        search_filters = {}
        if datetime_interval is not None:
            if datetime_interval.get("after", False):
                search_filters["$gte"] = datetime_interval["after"]

            if datetime_interval.get("before", False):
                search_filters["$lte"] = datetime_interval["before"]

            if datetime_interval.get("match", False):
                search_filters = datetime_interval["match"]

            return {"created": search_filters}
        return {}

    @staticmethod
    def _apply_duration_filter(pipeline, min_duration, max_duration):
        # type: (MongodbAggregatePipeline, Optional[int], Optional[int]) -> MongodbAggregatePipeline
        """
        Generate the filter required for comparing against :meth:`Job.duration`.

        Assumes that the first item of the pipeline is ``$match`` since steps must be applied before and after.
        Pipeline is modified inplace and returned as well.
        """
        if min_duration is not None or max_duration is not None:
            # validate values when both are provided, zero-minimum already enforced by schema validators
            if min_duration is not None and max_duration is not None and min_duration >= max_duration:
                raise JobInvalidParameter(json={
                    "code": "JobInvalidParameter",
                    "description": "Duration parameters are not forming a valid range.",
                    "cause": "Parameter 'minDuration' must be smaller than 'maxDuration'.",
                    "value": {"minDuration": min_duration, "maxDuration": max_duration}
                })

            # duration is not directly stored in the database (as it can change), it must be computed inplace
            duration_field = {
                "$addFields": {
                    "duration": {  # becomes 'null' if cannot be computed (e.g.: not started)
                        "$dateDiff": {
                            # compute the same way as Job.duration
                            "startDate": "$started",
                            "endDate": {"$cond": {"if": "$finished", "then": "$finished", "else": "$$NOW"}},
                            "unit": "second"
                        }
                    }
                }
            }
            pipeline.insert(0, duration_field)

            # apply duration search conditions
            duration_filter = {"$ne": None}
            if min_duration is not None:
                duration_filter["$gte"] = min_duration
            if max_duration is not None:
                duration_filter["$lte"] = max_duration
            pipeline[1]["$match"].update({"duration": duration_filter})
        return pipeline

    def clear_jobs(self):
        # type: () -> bool
        """
        Removes all jobs from `MongoDB` storage.
        """
        self.collection.drop()
        return True


class MongodbQuoteStore(StoreQuotes, MongodbStore):
    """
    Registry for quotes.

    Uses `MongoDB` to store quote attributes.
    """

    def __init__(self, *args, **kwargs):
        # type: (*Any, **Any) -> None
        db_args, db_kwargs = MongodbStore.get_args_kwargs(*args, **kwargs)
        StoreQuotes.__init__(self)
        MongodbStore.__init__(self, *db_args, **db_kwargs)

    def _apply_quote(self, quote, override=False):
        # type: (Quote, bool) -> Quote
        if not isinstance(quote, Quote):
            raise QuoteInstanceError(f"Invalid quote object: '{quote!r}'")
        try:
            if override:
                self.collection.update_one({"id": quote.id}, {"$set": quote.params()})
            else:
                self.collection.insert_one(quote.params())
            params = self.fetch_by_id(quote_id=quote.id)
        except Exception as ex:
            raise QuoteRegistrationError(f"Error occurred during quote registration: [{ex!r}]")
        if params is None:
            raise QuoteRegistrationError("Failed to retrieve registered quote.")
        return Quote(**params)

    def save_quote(self, quote):
        # type: (Quote) -> Quote
        """
        Stores a quote in `MongoDB` storage.
        """
        return self._apply_quote(quote, False)

    def update_quote(self, quote):
        # type: (Quote) -> Quote
        """
        Update quote parameters in `MongoDB` storage.
        """
        return self._apply_quote(quote, True)

    def fetch_by_id(self, quote_id):
        # type: (AnyUUID) -> Quote
        """
        Gets quote for given ``quote_id`` from `MongoDB` storage.
        """
        if isinstance(quote_id, str):
            quote_id = uuid.UUID(quote_id)
        quote = self.collection.find_one({"id": quote_id})
        if not quote:
            raise QuoteNotFound(f"Could not find quote matching: '{quote_id}'")
        return Quote(quote)

    def list_quotes(self):
        # type: (...) -> List[Quote]
        """
        Lists all quotes in `MongoDB` storage.
        """
        quotes = []
        for quote in self.collection.find().sort("id", pymongo.ASCENDING):
            quotes.append(Quote(quote))
        return quotes

    def find_quotes(self, process_id=None, page=0, limit=10, sort=None):
        # type: (Optional[str], int, int, Optional[str]) -> Tuple[List[Quote], int]
        """
        Finds all quotes in `MongoDB` storage matching search filters.

        Returns a tuple of filtered ``items`` and their ``count``, where ``items`` can have paging and be limited
        to a maximum per page, but ``count`` always indicate the `total` number of matches.
        """
        search_filters = {}

        if isinstance(process_id, str):
            search_filters["process"] = process_id

        if sort is None:
            sort = Sort.ID
        if sort not in SortMethods.QUOTE:
            raise QuoteNotFound(f"Invalid sorting method: '{sort!s}'")

        sort_order = pymongo.ASCENDING
        sort_criteria = [(sort, sort_order)]
        found = self.collection.find(search_filters)
        count = found.count()
        items = [Quote(item) for item in list(found.skip(page * limit).limit(limit).sort(sort_criteria))]
        return items, count


class MongodbBillStore(StoreBills, MongodbStore):
    """
    Registry for bills.

    Uses `MongoDB` to store bill attributes.
    """

    def __init__(self, *args, **kwargs):
        db_args, db_kwargs = MongodbStore.get_args_kwargs(*args, **kwargs)
        StoreBills.__init__(self)
        MongodbStore.__init__(self, *db_args, **db_kwargs)

    def save_bill(self, bill):
        # type: (Bill) -> Bill
        """
        Stores a bill in mongodb.
        """
        if not isinstance(bill, Bill):
            raise BillInstanceError(f"Invalid bill object: '{bill!r}'")
        try:
            self.collection.insert_one(bill.params())
            bill = self.fetch_by_id(bill_id=bill.id)
        except Exception as ex:
            raise BillRegistrationError(f"Error occurred during bill registration: [{ex!r}]")
        if bill is None:
            raise BillRegistrationError("Failed to retrieve registered bill.")
        return Bill(bill)

    def fetch_by_id(self, bill_id):
        # type: (str) -> Bill
        """
        Gets bill for given ``bill_id`` from `MongoDB` storage.
        """
        if isinstance(bill_id, str):
            bill_id = uuid.UUID(bill_id)
        bill = self.collection.find_one({"id": bill_id})
        if not bill:
            raise BillNotFound(f"Could not find bill matching: '{bill_id}'")
        return Bill(bill)

    def list_bills(self):
        # type: (...) -> List[Bill]
        """
        Lists all bills in `MongoDB` storage.
        """
        bills = []
        for bill in self.collection.find().sort(Sort.ID, pymongo.ASCENDING):
            bills.append(Bill(bill))
        return bills

    def find_bills(self, quote_id=None, page=0, limit=10, sort=None):
        # type: (Optional[str], int, int, Optional[str]) -> Tuple[List[Bill], int]
        """
        Finds all bills in `MongoDB` storage matching search filters.

        Returns a tuple of filtered ``items`` and their ``count``, where ``items`` can have paging and be limited
        to a maximum per page, but ``count`` always indicate the `total` number of matches.
        """
        search_filters = {}

        if isinstance(quote_id, str):
            search_filters["quote"] = quote_id

        if sort is None:
            sort = Sort.ID
        if sort not in SortMethods.BILL:
            raise BillNotFound(f"Invalid sorting method: '{sort!r}'")

        sort_order = pymongo.ASCENDING
        sort_criteria = [(sort, sort_order)]
        found = self.collection.find(search_filters)
        count = found.count()
        items = [Bill(item) for item in list(found.skip(page * limit).limit(limit).sort(sort_criteria))]
        return items, count


class MongodbVaultStore(StoreVault, MongodbStore):
    """
    Registry for vault files.

    Uses `MongoDB` to store vault files attributes.
    """

    def __init__(self, *args, **kwargs):
        # type: (*Any, **Any) -> None
        db_args, db_kwargs = MongodbStore.get_args_kwargs(*args, **kwargs)
        StoreVault.__init__(self)
        MongodbStore.__init__(self, *db_args, **db_kwargs)

    def get_file(self, file_id, nothrow=False):
        # type: (AnyUUID, bool) -> Optional[VaultFile]
        """
        Gets vault file for given ``file_id`` from `MongoDB` storage.

        :raises VaultFileNotFound: If the file does not exist and :paramref:`nothrow` was not requested.
        :returns: Found file if it exists or ``None`` if it doesn't exist and :paramref:`nothrow` was requested.
        """
        if isinstance(file_id, str):
            file_id = uuid.UUID(file_id)
        params = self.collection.find_one({"id": file_id})
        if not params:
            if nothrow:
                return None
            raise VaultFileNotFound(f"Could not find vault file matching: '{file_id}'")
        return VaultFile.from_params(**params)

    def save_file(self, file):
        # type: (VaultFile) -> None
        """
        Stores a vault file in `MongoDB` storage.
        """
        if not isinstance(file, VaultFile):
            raise VaultFileInstanceError(f"Invalid vault file object: '{file!r}'")
        try:
            self.collection.insert_one(file.params())
        except Exception as ex:
            raise VaultFileRegistrationError(f"Error occurred during vault file registration: [{ex!r}]")
        return None

    def delete_file(self, file):
        # type: (Union[VaultFile, AnyUUID]) -> bool
        """
        Removes vault file from `MongoDB` storage.
        """
        file_id = file.id if isinstance(file, VaultFile) else file
        if isinstance(file_id, str):
            file_id = uuid.UUID(file_id)
        return bool(self.collection.delete_one({"identifier": file_id}).deleted_count)
