import abc
from distutils.version import LooseVersion
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import datetime
    from typing import Dict, List, Optional, Tuple, Union

    from pyramid.request import Request
    from pywps import Process as ProcessWPS

    from weaver.datatype import Bill, Job, Process, Quote, Service, VaultFile
    from weaver.execute import AnyExecuteResponse
    from weaver.typedefs import (
        AnyUUID,
        AnyVersion,
        ExecutionInputs,
        ExecutionOutputs,
        DatetimeIntervalType,
        SettingsType,
        TypedDict
    )
    from weaver.visibility import AnyVisibility

    JobGroupCategory = TypedDict("JobGroupCategory",
                                 {"category": Dict[str, Optional[str]], "count": int, "jobs": List[Job]})
    JobSearchResult = Tuple[Union[List[Job], JobGroupCategory], int]


class StoreInterface(object, metaclass=abc.ABCMeta):
    type = None      # type: str
    settings = None  # type: SettingsType

    def __init__(self, settings=None):
        # type: (Optional[SettingsType]) -> None
        self.settings = settings
        if not self.type:
            raise NotImplementedError("Store 'type' must be overridden in inheriting class.")


class StoreServices(StoreInterface):
    type = "services"

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
    type = "processes"

    @abc.abstractmethod
    def save_process(self, process, overwrite=True):
        # type: (Union[Process, ProcessWPS], bool) -> Process
        raise NotImplementedError

    @abc.abstractmethod
    def delete_process(self, process_id, visibility=None):
        # type: (str, Optional[AnyVisibility]) -> bool
        raise NotImplementedError

    @abc.abstractmethod
    def list_processes(self,
                       visibility=None,     # type: Optional[AnyVisibility, List[AnyVisibility]]
                       page=None,           # type: Optional[int]
                       limit=None,          # type: Optional[int]
                       sort=None,           # type: Optional[str]
                       total=False,         # type: bool
                       ):                   # type: (...) -> Union[List[Process], Tuple[List[Process], int]]
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_by_id(self, process_id, visibility=None):
        # type: (str, Optional[AnyVisibility]) -> Process
        raise NotImplementedError

    @abc.abstractmethod
    def find_versions(self, process_id, version_format):
        # type: (str, VersionFormat) -> List[LooseVersion]
        raise NotImplementedError

    @abc.abstractmethod
    def update_version(self, process_id, version):
        # type: (str, AnyVersion) -> Process
        raise NotImplementedError

    @abc.abstractmethod
    def get_visibility(self, process_id):
        # type: (str) -> AnyVisibility
        raise NotImplementedError

    @abc.abstractmethod
    def set_visibility(self, process_id, visibility):
        # type: (str, AnyVisibility) -> None
        raise NotImplementedError

    @abc.abstractmethod
    def clear_processes(self):
        # type: () -> bool
        raise NotImplementedError


class StoreJobs(StoreInterface):
    type = "jobs"

    @abc.abstractmethod
    def save_job(self,
                 task_id,                   # type: str
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
        raise NotImplementedError

    @abc.abstractmethod
    def clear_jobs(self):
        # type: () -> bool
        raise NotImplementedError


class StoreQuotes(StoreInterface):
    type = "quotes"

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
        # type: (Optional[str], int, int, Optional[str]) -> Tuple[List[Quote], int]
        raise NotImplementedError

    @abc.abstractmethod
    def update_quote(self, quote):
        # type: (Quote) -> Quote
        raise NotImplementedError


class StoreBills(StoreInterface):
    type = "bills"

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
        # type: (Optional[str], int, int, Optional[str]) -> Tuple[List[Bill], int]
        raise NotImplementedError


class StoreVault(StoreInterface):
    type = "vault"

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
