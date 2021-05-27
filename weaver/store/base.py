import abc
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional, Tuple, Union
    from pyramid.request import Request
    from pywps import Process as ProcessWPS
    from weaver.datatype import Bill, Job, Process, Quote, Service
    from weaver.typedefs import AnyValue, Datetime, DatetimeIntervalType

    JobListAndCount = Tuple[List[Job], int]
    JobCategory = Dict[str, Union[AnyValue, Job]]
    JobCategoriesAndCount = Tuple[List[JobCategory], int]


class StoreInterface(object, metaclass=abc.ABCMeta):
    type = None

    def __init__(self):
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
        # type: (str, Optional[str]) -> Service
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
        # type: (str, Optional[str]) -> bool
        raise NotImplementedError

    @abc.abstractmethod
    def list_processes(self, visibility=None):
        # type: (Optional[str]) -> List[Process]
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_by_id(self, process_id, visibility=None):
        # type: (str, Optional[str]) -> Process
        raise NotImplementedError

    @abc.abstractmethod
    def get_visibility(self, process_id):
        # type: (str) -> str
        raise NotImplementedError

    @abc.abstractmethod
    def set_visibility(self, process_id, visibility):
        # type: (str, str) -> None
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
                 inputs=None,               # type: Optional[List[Any]]
                 is_workflow=False,         # type: bool
                 is_local=False,            # type: bool
                 user_id=None,              # type: Optional[int]
                 execute_async=True,        # type: bool
                 custom_tags=None,          # type: Optional[List[str]]
                 access=None,               # type: Optional[str]
                 notification_email=None,   # type: Optional[str]
                 accept_language=None,      # type: Optional[str]
                 created=None,              # type: Datetime
                 ):                         # type: (...) -> Job
        raise NotImplementedError

    @abc.abstractmethod
    def update_job(self, job):
        # type: (Job) -> Job
        raise NotImplementedError

    @abc.abstractmethod
    def delete_job(self, job_id):
        # type: (str) -> bool
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_by_id(self, job_id):
        # type: (str) -> Job
        raise NotImplementedError

    @abc.abstractmethod
    def list_jobs(self):
        # type: () -> List[Job]
        raise NotImplementedError

    @abc.abstractmethod
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
        # type: (str) -> Quote
        raise NotImplementedError

    @abc.abstractmethod
    def list_quotes(self):
        # type: (...) -> List[Quote]
        raise NotImplementedError

    @abc.abstractmethod
    def find_quotes(self, process_id=None, page=0, limit=10, sort=None):
        # type: (Optional[str], int, int, Optional[str]) -> Tuple[List[Quote], int]
        raise NotImplementedError


class StoreBills(StoreInterface):
    type = "bills"

    @abc.abstractmethod
    def save_bill(self, bill):
        # type: (Bill) -> Bill
        raise NotImplementedError

    @abc.abstractmethod
    def fetch_by_id(self, bill_id):
        # type: (str) -> Bill
        raise NotImplementedError

    @abc.abstractmethod
    def list_bills(self):
        # type: (...) -> List[Bill]
        raise NotImplementedError

    @abc.abstractmethod
    def find_bills(self, quote_id=None, page=0, limit=10, sort=None):
        # type: (Optional[str], int, int, Optional[str]) -> Tuple[List[Bill], int]
        raise NotImplementedError
