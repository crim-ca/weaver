import abc
from typing import TYPE_CHECKING
from typing_extensions import Literal, get_args

from weaver.utils import VersionFormat

if TYPE_CHECKING:
    import datetime
    from typing import Any, Dict, List, Optional, Tuple, Union

    from pyramid.request import Request
    from pywps import Process as ProcessWPS

    from weaver.datatype import Bill, Job, Process, Quote, Service, VaultFile
    from weaver.execute import AnyExecuteMode, AnyExecuteResponse, AnyExecuteReturnPreference
    from weaver.sort import AnySortType
    from weaver.status import AnyStatusSearch, AnyStatusType
    from weaver.typedefs import (
        AnyProcessRef,
        AnyServiceRef,
        AnyUUID,
        AnyVersion,
        DatetimeIntervalType,
        ExecutionInputs,
        ExecutionOutputs,
        ExecutionSubscribers,
        JSON,
        SettingsType,
        TypedDict
    )
    from weaver.visibility import AnyVisibility

    JobGroupCategory = TypedDict("JobGroupCategory",
                                 {"category": Dict[str, Optional[str]], "count": int, "jobs": List[Job]})
    JobSearchResult = Tuple[Union[List[Job], JobGroupCategory], int]


StoreServicesType = Literal["services"]
StoreProcessesType = Literal["processes"]
StoreJobsType = Literal["jobs"]
StoreBillsType = Literal["bills"]
StoreQuotesType = Literal["quotes"]
StoreVaultType = Literal["vault"]
StoreTypeName = Literal[
    StoreBillsType,
    StoreJobsType,
    StoreProcessesType,
    StoreQuotesType,
    StoreServicesType,
    StoreVaultType
]


class StoreInterface(object, metaclass=abc.ABCMeta):
    type = None      # type: StoreTypeName
    settings = None  # type: SettingsType

    def __init__(self, settings=None):
        # type: (Optional[SettingsType]) -> None
        self.settings = settings
        if not self.type:
            raise NotImplementedError("Store 'type' must be overridden in inheriting class.")


class StoreServices(StoreInterface):
    type = get_args(StoreServicesType)[0]

    @abc.abstractmethod
    def save_service(self, service, overwrite=True):
        # type: (Service, bool) -> Service
        raise NotImplementedError

    @abc.abstractmethod
    def delete_service(self, name):
        # type: (str) -> bool
        raise NotImplementedError

    @abc.abstractmethod
    def list_services(self):
        # type: () -> List[Service]
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_by_name(self, name, visibility=None):
        # type: (str, Optional[AnyVisibility]) -> Service
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_by_url(self, url):
        # type: (str) -> Service
        raise NotImplementedError

    @abc.abstractmethod
    def clear_services(self):
        # type: () -> bool
        raise NotImplementedError


class StoreProcesses(StoreInterface):
    type = get_args(StoreProcessesType)[0]

    @abc.abstractmethod
    def save_process(self, process, overwrite=True):
        # type: (Union[Process, ProcessWPS], bool) -> Process
        raise NotImplementedError

    @abc.abstractmethod
    def delete_process(self, process_id, visibility=None):
        # type: (AnyProcessRef, Optional[AnyVisibility]) -> bool
        raise NotImplementedError

    @abc.abstractmethod
    def list_processes(self,
                       visibility=None,     # type: Optional[AnyVisibility, List[AnyVisibility]]
                       page=None,           # type: Optional[int]
                       limit=None,          # type: Optional[int]
                       sort=None,           # type: Optional[AnySortType]
                       total=False,         # type: bool
                       revisions=False,     # type: bool
                       process=None,        # type: Optional[str]
                       ):                   # type: (...) -> Union[List[Process], Tuple[List[Process], int]]
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_by_id(self, process_id, visibility=None):
        # type: (AnyProcessRef, Optional[AnyVisibility]) -> Process
        raise NotImplementedError

    @abc.abstractmethod
    def find_versions(self, process_id, version_format=VersionFormat.OBJECT):
        # type: (AnyProcessRef, VersionFormat) -> List[AnyVersion]
        raise NotImplementedError

    @abc.abstractmethod
    def update_version(self, process_id, version):
        # type: (AnyProcessRef, AnyVersion) -> Process
        raise NotImplementedError

    @abc.abstractmethod
    def get_estimator(self, process_id):
        # type: (AnyProcessRef) -> JSON
        raise NotImplementedError

    @abc.abstractmethod
    def set_estimator(self, process_id, estimator):
        # type: (AnyProcessRef, JSON) -> None
        raise NotImplementedError

    @abc.abstractmethod
    def get_visibility(self, process_id):
        # type: (AnyProcessRef) -> AnyVisibility
        raise NotImplementedError

    @abc.abstractmethod
    def set_visibility(self, process_id, visibility):
        # type: (AnyProcessRef, AnyVisibility) -> None
        raise NotImplementedError

    @abc.abstractmethod
    def clear_processes(self):
        # type: () -> bool
        raise NotImplementedError


class StoreJobs(StoreInterface):
    type = get_args(StoreJobsType)[0]

    @abc.abstractmethod
    def save_job(self,
                 task_id,                   # type: str
                 process,                   # type: AnyProcessRef
                 service=None,              # type: Optional[AnyServiceRef]
                 inputs=None,               # type: Optional[ExecutionInputs]
                 outputs=None,              # type: Optional[ExecutionOutputs]
                 is_workflow=False,         # type: bool
                 is_local=False,            # type: bool
                 execute_mode=None,         # type: Optional[AnyExecuteMode]
                 execute_wait=None,         # type: Optional[int]
                 execute_response=None,     # type: Optional[AnyExecuteResponse]
                 execute_return=None,       # type: Optional[AnyExecuteReturnPreference]
                 custom_tags=None,          # type: Optional[List[str]]
                 user_id=None,              # type: Optional[int]
                 access=None,               # type: Optional[AnyVisibility]
                 context=None,              # type: Optional[str]
                 subscribers=None,          # type: Optional[ExecutionSubscribers]
                 accept_type=None,          # type: Optional[str]
                 accept_language=None,      # type: Optional[str]
                 created=None,              # type: Optional[datetime.datetime]
                 status=None,               # type: Optional[AnyStatusType]
                 ):                         # type: (...) -> Job
        raise NotImplementedError

    @abc.abstractmethod
    def batch_update_jobs(self, job_filter, job_update):
        # type: (Dict[str, Any], Dict[str, Any]) -> int
        raise NotImplementedError

    @abc.abstractmethod
    def update_job(self, job):
        # type: (Job) -> Job
        raise NotImplementedError

    @abc.abstractmethod
    def delete_job(self, job_id):
        # type: (AnyUUID) -> bool
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_by_id(self, job_id):
        # type: (AnyUUID) -> Job
        raise NotImplementedError

    @abc.abstractmethod
    def list_jobs(self):
        # type: () -> List[Job]
        raise NotImplementedError

    @abc.abstractmethod
    def find_jobs(self,
                  process=None,             # type: Optional[str]
                  service=None,             # type: Optional[str]
                  job_type=None,            # type: Optional[str]
                  tags=None,                # type: Optional[List[str]]
                  access=None,              # type: Optional[str]
                  status=None,              # type: Optional[AnyStatusSearch, List[AnyStatusSearch]]
                  sort=None,                # type: Optional[AnySortType]
                  page=0,                   # type: Optional[int]
                  limit=10,                 # type: Optional[int]
                  min_duration=None,        # type: Optional[int]
                  max_duration=None,        # type: Optional[int]
                  datetime_interval=None,   # type: Optional[DatetimeIntervalType]
                  group_by=None,            # type: Optional[Union[str, List[str]]]
                  request=None,             # type: Optional[Request]
                  ):                        # type: (...) -> JobSearchResult
        raise NotImplementedError

    @abc.abstractmethod
    def clear_jobs(self):
        # type: () -> bool
        raise NotImplementedError


class StoreQuotes(StoreInterface):
    type = get_args(StoreQuotesType)[0]

    @abc.abstractmethod
    def save_quote(self, quote):
        # type: (Quote) -> Quote
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_by_id(self, quote_id):
        # type: (AnyUUID) -> Quote
        raise NotImplementedError

    @abc.abstractmethod
    def list_quotes(self):
        # type: (...) -> List[Quote]
        raise NotImplementedError

    @abc.abstractmethod
    def find_quotes(self, process_id=None, page=0, limit=10, sort=None):
        # type: (Optional[str], int, int, Optional[AnySortType]) -> Tuple[List[Quote], int]
        raise NotImplementedError

    @abc.abstractmethod
    def update_quote(self, quote):
        # type: (Quote) -> Quote
        raise NotImplementedError


class StoreBills(StoreInterface):
    type = get_args(StoreBillsType)[0]

    @abc.abstractmethod
    def save_bill(self, bill):
        # type: (Bill) -> Bill
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_by_id(self, bill_id):
        # type: (AnyUUID) -> Bill
        raise NotImplementedError

    @abc.abstractmethod
    def list_bills(self):
        # type: (...) -> List[Bill]
        raise NotImplementedError

    @abc.abstractmethod
    def find_bills(self, quote_id=None, page=0, limit=10, sort=None):
        # type: (Optional[str], int, int, Optional[AnySortType]) -> Tuple[List[Bill], int]
        raise NotImplementedError


class StoreVault(StoreInterface):
    type = get_args(StoreVaultType)[0]

    @abc.abstractmethod
    def get_file(self, file_id, nothrow=False):
        # type: (AnyUUID, bool) -> VaultFile
        raise NotImplementedError

    @abc.abstractmethod
    def save_file(self, file):
        # type: (VaultFile) -> None
        raise NotImplementedError

    @abc.abstractmethod
    def delete_file(self, file):
        # type: (Union[VaultFile, AnyUUID]) -> bool
        raise NotImplementedError
