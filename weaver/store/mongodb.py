"""
Stores to read/write data to from/to `MongoDB` using pymongo.
"""

import logging
from typing import TYPE_CHECKING

import pymongo
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError
from pyramid.request import Request
from pywps import Process as ProcessWPS

from weaver.datatype import Bill, Job, Process, Quote, Service
from weaver.exceptions import (
    BillInstanceError,
    BillNotFound,
    BillRegistrationError,
    JobNotFound,
    JobRegistrationError,
    JobUpdateError,
    ProcessInstanceError,
    ProcessNotAccessible,
    ProcessNotFound,
    ProcessRegistrationError,
    QuoteInstanceError,
    QuoteNotFound,
    QuoteRegistrationError,
    ServiceNotAccessible,
    ServiceNotFound,
    ServiceRegistrationError
)
from weaver.execute import EXECUTE_MODE_ASYNC, EXECUTE_MODE_SYNC
from weaver.processes.types import PROCESS_APPLICATION, PROCESS_WORKFLOW, PROCESS_WPS_LOCAL
from weaver.sort import (
    BILL_SORT_VALUES,
    JOB_SORT_VALUES,
    QUOTE_SORT_VALUES,
    SORT_CREATED,
    SORT_FINISHED,
    SORT_ID,
    SORT_USER
)
from weaver.status import JOB_STATUS_CATEGORIES, STATUS_ACCEPTED, map_status
from weaver.store.base import StoreBills, StoreJobs, StoreProcesses, StoreQuotes, StoreServices
from weaver.utils import get_base_url, get_sane_name, get_weaver_url, islambda, now
from weaver.visibility import VISIBILITY_PRIVATE, VISIBILITY_PUBLIC, VISIBILITY_VALUES
from weaver.wps.utils import get_wps_url

if TYPE_CHECKING:
    import datetime
    from typing import Any, Callable, Dict, List, Optional, Tuple, Union
    from pymongo.collection import Collection

    from weaver.store.base import DatetimeIntervalType, JobCategoriesAndCount, JobListAndCount
    from weaver.typedefs import AnyProcess, AnyProcessType

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
    Registry for OWS services. Uses `MongoDB` to store service url and attributes.
    """

    def __init__(self, *args, **kwargs):
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
        # type: (str, Optional[str]) -> Service
        """
        Gets service for given ``name`` from `MongoDB` storage.
        """
        service = self.collection.find_one({"name": name})
        if not service:
            raise ServiceNotFound("Service '{}' could not be found.".format(name))
        service = Service(service)
        same_visibility = (service.public and visibility == VISIBILITY_PUBLIC) or \
                          (not service.public and visibility == VISIBILITY_PRIVATE)
        if visibility is not None and not same_visibility:
            raise ServiceNotAccessible("Service '{}' cannot be accessed.".format(name))
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


class MongodbProcessStore(StoreProcesses, MongodbStore):
    """
    Registry for processes. Uses `MongoDB` to store processes and attributes.
    """

    def __init__(self, *args, **kwargs):
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
            raise ProcessInstanceError("Unsupported process type '{}'".format(type(process)))

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
        # type: (AnyProcess, Union[Dict[AnyProcessType, Callable[[], Any]], Callable[[], Any]]) -> Any
        """
        Takes a lambda expression or a dict of process-specific lambda expressions to retrieve a field.
        Validates that the passed process object is one of the supported types.

        :param process: process to retrieve the field from.
        :param function_dict: lambda or dict of lambda of process type
        :return: retrieved field if the type was supported
        :raises ProcessInstanceError: invalid process type
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
            raise ProcessInstanceError("Unsupported process type '{}'".format(type(process)))

    def _get_process_id(self, process):
        # type: (AnyProcess) -> str
        return self._get_process_field(process, lambda: process.identifier)

    def _get_process_type(self, process):
        # type: (AnyProcess) -> str
        return self._get_process_field(process, {
            Process: lambda: process.type,
            ProcessWPS: lambda: getattr(process, "type", PROCESS_WPS_LOCAL)
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
                raise ProcessRegistrationError("Process '{}' already registered.".format(sane_name))
        process.identifier = sane_name  # must use property getter/setter to match both 'Process' types
        self._add_process(process)
        return self.fetch_by_id(sane_name)

    def delete_process(self, process_id, visibility=None):
        # type: (str, Optional[str]) -> bool
        """
        Removes process from database, optionally filtered by visibility.
        If ``visibility=None``, the process is deleted (if existing) regardless of its visibility value.
        """
        sane_name = get_sane_name(process_id, **self.sane_name_config)
        process = self.fetch_by_id(sane_name, visibility=visibility)
        if not process:
            raise ProcessNotFound("Process '{}' could not be found.".format(sane_name))
        return bool(self.collection.delete_one({"identifier": sane_name}).deleted_count)

    def list_processes(self, visibility=None):
        # type: (Optional[str]) -> List[Process]
        """
        Lists all processes in database, optionally filtered by `visibility`.

        :param visibility: One value amongst `weaver.visibility`.
        """
        db_processes = []
        search_filters = {}
        if visibility is None:
            visibility = VISIBILITY_VALUES
        if isinstance(visibility, str):
            visibility = [visibility]
        for v in visibility:
            if v not in VISIBILITY_VALUES:
                raise ValueError("Invalid visibility value '{0!s}' is not one of {1!s}"
                                 .format(v, list(VISIBILITY_VALUES)))
        search_filters["visibility"] = {"$in": list(visibility)}
        for process in self.collection.find(search_filters).sort("identifier", pymongo.ASCENDING):
            db_processes.append(Process(process))
        return db_processes

    def fetch_by_id(self, process_id, visibility=None):
        # type: (str, Optional[str]) -> Process
        """
        Get process for given :paramref:`process_id` from storage, optionally filtered by :paramref:`visibility`.
        If ``visibility=None``, the process is retrieved (if existing) regardless of its visibility value.

        :param process_id: process identifier
        :param visibility: one value amongst :py:mod:`weaver.visibility`.
        :return: An instance of :class:`weaver.datatype.Process`.
        """
        sane_name = get_sane_name(process_id, **self.sane_name_config)
        process = self.collection.find_one({"identifier": sane_name})
        if not process:
            raise ProcessNotFound("Process '{}' could not be found.".format(sane_name))
        process = Process(process)
        if visibility is not None and process.visibility != visibility:
            raise ProcessNotAccessible("Process '{}' cannot be accessed.".format(sane_name))
        return process

    def get_visibility(self, process_id):
        # type: (str) -> str
        """
        Get `visibility` of a process.

        :return: One value amongst `weaver.visibility`.
        """
        process = self.fetch_by_id(process_id)
        return process.visibility

    def set_visibility(self, process_id, visibility):
        # type: (str, str) -> None
        """
        Set `visibility` of a process.

        :param visibility: One value amongst `weaver.visibility`.
        :param process_id:
        :raises TypeError: when :paramref:`visibility` is not :class:`str`.
        :raises ValueError: when :paramref:`visibility` is not one of :py:data:`weaver.visibility.VISIBILITY_VALUES`.
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


class MongodbJobStore(StoreJobs, MongodbStore):
    """
    Registry for process jobs tracking. Uses `MongoDB` to store job attributes.
    """

    def __init__(self, *args, **kwargs):
        db_args, db_kwargs = MongodbStore.get_args_kwargs(*args, **kwargs)
        StoreJobs.__init__(self)
        MongodbStore.__init__(self, *db_args, **db_kwargs)

    def save_job(self,
                 task_id,                   # type: str
                 process,                   # type: str
                 service=None,              # type: Optional[str]
                 inputs=None,               # type: Optional[List[Any]]
                 is_workflow=False,         # type: bool
                 is_local=False,            # type: bool
                 user_id=None,              # type: Optional[int]
                 execute_async=True,        # type: bool
                 custom_tags=None,          # type: Optional[List[str]]
                 access=None,               # type: Optional[str]
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
                tags.append(PROCESS_WORKFLOW)
            else:
                tags.append(PROCESS_APPLICATION)
            if execute_async:
                tags.append(EXECUTE_MODE_ASYNC)
            else:
                tags.append(EXECUTE_MODE_SYNC)
            if not access:
                access = VISIBILITY_PRIVATE

            new_job = Job({
                "task_id": task_id,
                "user_id": user_id,
                "service": service,     # provider identifier (WPS service)
                "process": process,     # process identifier (WPS request)
                "inputs": inputs,
                "status": map_status(STATUS_ACCEPTED),
                "execute_async": execute_async,
                "is_workflow": is_workflow,
                "is_local": is_local,
                "created": created if created else now(),
                "tags": list(set(tags)),  # remove duplicates
                "access": access,
                "notification_email": notification_email,
                "accept_language": accept_language,
            })
            self.collection.insert_one(new_job.params())
            job = self.fetch_by_id(job_id=new_job.id)
        except Exception as ex:
            raise JobRegistrationError("Error occurred during job registration: [{}]".format(repr(ex)))
        if job is None:
            raise JobRegistrationError("Failed to retrieve registered job.")
        return job

    def update_job(self, job):
        # type: (Job) -> Job
        """
        Updates a job parameters in `MongoDB` storage.
        :param job: instance of ``weaver.datatype.Job``.
        """
        try:
            result = self.collection.update_one({"id": job.id}, {"$set": job.params()})
            if result.acknowledged and result.matched_count == 1:
                return self.fetch_by_id(job.id)
        except Exception as ex:
            raise JobUpdateError("Error occurred during job update: [{}]".format(repr(ex)))
        raise JobUpdateError("Failed to update specified job: '{}'".format(str(job)))

    def delete_job(self, job_id):
        # type: (str) -> bool
        """
        Removes job from `MongoDB` storage.
        """
        self.collection.delete_one({"id": job_id})
        return True

    def fetch_by_id(self, job_id):
        # type: (str) -> Job
        """
        Gets job for given ``job_id`` from `MongoDB` storage.
        """
        job = self.collection.find_one({"id": job_id})
        if not job:
            raise JobNotFound("Could not find job matching: '{}'".format(job_id))
        return Job(job)

    def list_jobs(self):
        # type: () -> List[Job]
        """
        Lists all jobs in `MongoDB` storage.
        For user-specific access to available jobs, use :meth:`MongodbJobStore.find_jobs` instead.
        """
        jobs = []
        for job in self.collection.find().sort("id", ASCENDING):
            jobs.append(Job(job))
        return jobs

    def find_jobs(self,
                  process=None,             # type: Optional[str]
                  service=None,             # type: Optional[str]
                  tags=None,                # type: Optional[List[str]]
                  access=None,              # type: Optional[str]
                  notification_email=None,  # type: Optional[str]
                  status=None,              # type: Optional[str]
                  sort=None,                # type: Optional[str]
                  page=0,                   # type: int
                  limit=10,                 # type: int
                  datetime=None,            # type: Optional[DatetimeIntervalType]
                  group_by=None,            # type: Optional[Union[str, List[str]]]
                  request=None,             # type: Optional[Request]
                  ):                        # type: (...) -> Union[JobListAndCount, JobCategoriesAndCount]
        """
        Finds all jobs in `MongoDB` storage matching search filters to obtain results with requested paging or grouping.

        :param request: request that lead to this call to obtain permissions and user id.
        :param process: process name to filter matching jobs.
        :param service: service name to filter matching jobs.
        :param tags: list of tags to filter matching jobs.
        :param access: access visibility to filter matching jobs (default: :py:data:`VISIBILITY_PUBLIC`).
        :param notification_email: notification email to filter matching jobs.
        :param status: status to filter matching jobs.
        :param sort: field which is used for sorting results (default: creation date, descending).
        :param page: page number to return when using result paging (only when not using ``group_by``).
        :param limit: number of jobs per page when using result paging (only when not using ``group_by``).
        :param datetime: field used for filtering data by creation date with a given date or interval of date.
        :param group_by: one or many fields specifying categories to form matching groups of jobs (paging disabled).

        :returns: (list of jobs matching paging OR list of {categories, list of jobs, count}) AND total of matched job

        Example:

            Using paging (default), result will be in the form::

                (
                    [Job(1), Job(2), Job(3), ...],
                    <total>
                )

            Where ``<total>`` will indicate the complete count of matched jobs with filters, but the list of jobs
            will be limited only to ``page`` index and ``limit`` specified.

            Using grouping with a list of field specified with ``group_by``, results will be in the form::

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
        """

        if any(v in tags for v in VISIBILITY_VALUES):
            raise ValueError("Visibility values not acceptable in 'tags', use 'access' instead.")

        search_filters = {}

        if not request:
            search_filters.setdefault("access", VISIBILITY_PUBLIC)
        else:
            if request.has_permission("admin") and access in VISIBILITY_VALUES:
                search_filters["access"] = access
            else:
                user_id = request.authenticated_userid
                if user_id is not None:
                    search_filters["user_id"] = user_id
                    if access in VISIBILITY_VALUES:
                        search_filters["access"] = access
                else:
                    search_filters["access"] = VISIBILITY_PUBLIC

        if tags:
            search_filters["tags"] = {"$all": tags}

        if status in JOB_STATUS_CATEGORIES:
            search_filters["status"] = {"$in": JOB_STATUS_CATEGORIES[status]}
        elif status:
            search_filters["status"] = status

        if notification_email is not None:
            search_filters["notification_email"] = notification_email

        if process is not None:
            search_filters["process"] = process

        if service is not None:
            search_filters["service"] = service

        if datetime is not None:
            query = {}

            if datetime.get("after", False):
                query["$gte"] = datetime["after"]

            if datetime.get("before", False):
                query["$lte"] = datetime["before"]

            if datetime.get("match", False):
                query = datetime["match"]

            search_filters["created"] = query

        if sort is None:
            sort = SORT_CREATED
        elif sort == SORT_USER:
            sort = "user_id"
        if sort not in JOB_SORT_VALUES:
            raise JobNotFound("Invalid sorting method: '{}'".format(repr(sort)))
        sort_order = DESCENDING if sort in (SORT_FINISHED, SORT_CREATED) else ASCENDING
        sort_criteria = {sort: sort_order}

        # minimal operation, only search for matches and sort them
        pipeline = [{"$match": search_filters}, {"$sort": sort_criteria}]

        # results by group categories
        if group_by:
            group_by = [group_by] if isinstance(group_by, str) else group_by  # type: List[str]
            group_categories = {field: "$" + field for field in group_by}   # fields that can generate groups
            pipeline.extend([{
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
            }])
            found = self.collection.aggregate(pipeline)
            items = [{k: (v if k != "jobs" else [Job(j) for j in v])    # convert to Job object where applicable
                      for k, v in i.items()} for i in found]

        # results with paging
        else:
            pipeline.extend([{"$skip": page * limit}, {"$limit": limit}])
            found = self.collection.aggregate(pipeline)
            items = [Job(item) for item in list(found)]

        total = self.collection.count_documents(search_filters)
        return items, total

    def clear_jobs(self):
        # type: () -> bool
        """
        Removes all jobs from `MongoDB` storage.
        """
        self.collection.drop()
        return True


class MongodbQuoteStore(StoreQuotes, MongodbStore):
    """
    Registry for quotes. Uses `MongoDB` to store quote attributes.
    """

    def __init__(self, *args, **kwargs):
        db_args, db_kwargs = MongodbStore.get_args_kwargs(*args, **kwargs)
        StoreQuotes.__init__(self)
        MongodbStore.__init__(self, *db_args, **db_kwargs)

    def save_quote(self, quote):
        # type: (Quote) -> Quote
        """
        Stores a quote in mongodb.
        """
        if not isinstance(quote, Quote):
            raise QuoteInstanceError("Invalid quote object: '{}'".format(repr(quote)))
        try:
            self.collection.insert_one(quote.params())
            quote = self.fetch_by_id(quote_id=quote.id)
        except Exception as ex:
            raise QuoteRegistrationError("Error occurred during quote registration: [{}]".format(repr(ex)))
        if quote is None:
            raise QuoteRegistrationError("Failed to retrieve registered quote.")
        return quote

    def fetch_by_id(self, quote_id):
        # type: (str) -> Quote
        """
        Gets quote for given ``quote_id`` from `MongoDB` storage.
        """
        quote = self.collection.find_one({"id": quote_id})
        if not quote:
            raise QuoteNotFound("Could not find quote matching: '{}'".format(quote_id))
        return Quote(quote)

    def list_quotes(self):
        # type: (...) -> List[Quote]
        """
        Lists all quotes in `MongoDB` storage.
        """
        quotes = []
        for quote in self.collection.find().sort("id", ASCENDING):
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
            sort = SORT_ID
        if sort not in QUOTE_SORT_VALUES:
            raise QuoteNotFound("Invalid sorting method: '{!s}'".format(sort))

        sort_order = ASCENDING
        sort_criteria = [(sort, sort_order)]
        found = self.collection.find(search_filters)
        count = found.count()
        items = [Quote(item) for item in list(found.skip(page * limit).limit(limit).sort(sort_criteria))]
        return items, count


class MongodbBillStore(StoreBills, MongodbStore):
    """
    Registry for bills. Uses `MongoDB` to store bill attributes.
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
            raise BillInstanceError("Invalid bill object: '{}'".format(repr(bill)))
        try:
            self.collection.insert_one(bill.params())
            bill = self.fetch_by_id(bill_id=bill.id)
        except Exception as ex:
            raise BillRegistrationError("Error occurred during bill registration: [{}]".format(repr(ex)))
        if bill is None:
            raise BillRegistrationError("Failed to retrieve registered bill.")
        return Bill(bill)

    def fetch_by_id(self, bill_id):
        # type: (str) -> Bill
        """
        Gets bill for given ``bill_id`` from `MongoDB` storage.
        """
        bill = self.collection.find_one({"id": bill_id})
        if not bill:
            raise BillNotFound("Could not find bill matching: '{}'".format(bill_id))
        return Bill(bill)

    def list_bills(self):
        # type: (...) -> List[Bill]
        """
        Lists all bills in `MongoDB` storage.
        """
        bills = []
        for bill in self.collection.find().sort("id", ASCENDING):
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
            sort = SORT_ID
        if sort not in BILL_SORT_VALUES:
            raise BillNotFound("Invalid sorting method: '{}'".format(repr(sort)))

        sort_order = ASCENDING
        sort_criteria = [(sort, sort_order)]
        found = self.collection.find(search_filters)
        count = found.count()
        items = [Bill(item) for item in list(found.skip(page * limit).limit(limit).sort(sort_criteria))]
        return items, count
