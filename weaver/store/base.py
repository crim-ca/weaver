"""
Store adapters to persist and retrieve data during the weaver process or
for later use. For example an access token storage and a service registry.

This module provides base classes that can be extended to implement your own
solution specific to your needs.

The implementation is based on `python-oauth2 <http://python-oauth2.readthedocs.io/en/latest/>`_.
"""
from pyramid.request import Request
from typing import Any, Optional, List, Union, AnyStr, Tuple
from weaver.datatype import Job, Service, Process, Quote, Bill
# noinspection PyPackageRequirements
from pywps import Process as ProcessWPS


class StoreInterface(object):
    type = None

    def __init__(self):
        if not self.type:
            raise ValueError("Store 'type' must be overridden in inheriting class.")


class ServiceStore(StoreInterface):
    """
    Storage for OWS services.
    """
    type = 'services'

    def save_service(self, service, overwrite=True, request=None):
        # type: (Service, Optional[bool], Optional[Request]) -> Service
        """
        Stores an OWS service in storage.
        """
        raise NotImplementedError

    def delete_service(self, name, request=None):
        # type: (AnyStr, Optional[Request]) -> bool
        """
        Removes service from database.
        """
        raise NotImplementedError

    def list_services(self, request=None):
        # type: (Optional[Request]) -> List[Service]
        """
        Lists all services in database.
        """
        raise NotImplementedError

    def fetch_by_name(self, name, visibility=None, request=None):
        # type: (AnyStr, Optional[AnyStr], Optional[Request]) -> Service
        """
        Get service for given ``name`` from storage.
        """
        raise NotImplementedError

    def fetch_by_url(self, url, request=None):
        # type: (AnyStr, Optional[Request]) -> Service
        """
        Get service for given ``url`` from storage.
        """
        raise NotImplementedError

    def clear_services(self, request=None):
        # type: (Optional[Request]) -> bool
        """
        Removes all OWS services from storage.
        """
        raise NotImplementedError


class ProcessStore(StoreInterface):
    """
    Storage for local WPS processes.
    """
    type = 'processes'

    def save_process(self, process, overwrite=True, request=None):
        # type: (Union[Process, ProcessWPS], Optional[bool], Optional[Request]) -> Process
        """
        Stores a WPS process in storage.
        """
        raise NotImplementedError

    def delete_process(self, process_id, visibility=None, request=None):
        # type: (AnyStr, Optional[AnyStr], Optional[Request]) -> bool
        """
        Removes process from database, optionally filtered by visibility.
        If visibility isn't specified (`None`), the process is deleted (if existing)
        regardless of its visibility value.
        """
        raise NotImplementedError

    def list_processes(self, visibility=None, request=None):
        # type: (Optional[AnyStr], Optional[Request]) -> List[Process]
        """
        Lists all processes in database, optionally filtered by visibility.

        :param visibility: one value amongst `weaver.visibility`.
        :param request:
        """
        raise NotImplementedError

    def fetch_by_id(self, process_id, visibility=None, request=None):
        # type: (AnyStr, Optional[AnyStr], Optional[Request]) -> Process
        """
        Get process for given ``id`` from storage, optionally filtered by visibility.
        If visibility isn't specified (`None`), the process is retrieved (if existing)
        regardless of its visibility value.

        :param process_id: process identifier
        :param visibility: one value amongst `weaver.visibility`.
        :param request:
        :return: An instance of :class:`weaver.datatype.Process`.
        """
        raise NotImplementedError

    def get_visibility(self, process_id, request=None):
        # type: (AnyStr, Optional[Request]) -> AnyStr
        """
        Get visibility of a process.

        :return: one value amongst `weaver.visibility`.
        """
        raise NotImplementedError

    def set_visibility(self, process_id, visibility, request=None):
        # type: (AnyStr, AnyStr, Optional[Request]) -> None
        """
        Set visibility of a process.

        :param visibility: One value amongst `weaver.visibility`.
        :param process_id:
        :param request:
        :raises: TypeError or ValueError in case of invalid parameter.
        """
        raise NotImplementedError

    def clear_processes(self, request=None):
        # type: (Optional[Request]) -> bool
        """
        Clears all processes from the store.
        """
        raise NotImplementedError


class JobStore(StoreInterface):
    """
    Storage for job tracking.
    """
    type = 'jobs'

    def save_job(self,
                 task_id,               # type: AnyStr
                 process,               # type: AnyStr
                 service=None,          # type: Optional[AnyStr]
                 inputs=None,           # type: Optional[List[Any]]
                 is_workflow=False,     # type: Optional[bool]
                 user_id=None,          # type: Optional[int]
                 execute_async=True,    # type: Optional[bool]
                 custom_tags=None,      # type: Optional[List[AnyStr]]
                 access=None,           # type: Optional[AnyStr]
                 ):                     # type: (...) -> Job
        """
        Stores a job in storage.
        """
        raise NotImplementedError

    def update_job(self, job):
        # type: (Job) -> Job
        """
        Updates a job parameters in mongodb storage.
        """
        raise NotImplementedError

    def delete_job(self, name, request=None):
        # type: (AnyStr, Optional[Request]) -> bool
        """
        Removes job from database.
        """
        raise NotImplementedError

    def fetch_by_id(self, job_id, request=None):
        # type: (AnyStr, Optional[Request]) -> Job
        """
        Get job for given ``job_id`` from storage.
        """
        raise NotImplementedError

    def list_jobs(self, request=None):
        # type: (Optional[Request]) -> List[Job]
        """
        Lists all jobs in database.
        """
        raise NotImplementedError

    def find_jobs(self,
                  request,          # type: Request
                  page=0,           # type: Optional[int]
                  limit=10,         # type: Optional[int]
                  process=None,     # type: Optional[AnyStr]
                  service=None,     # type: Optional[AnyStr]
                  tags=None,        # type: Optional[List[AnyStr]]
                  access=None,      # type: Optional[AnyStr]
                  status=None,      # type: Optional[AnyStr]
                  sort=None,        # type: Optional[AnyStr]
                  ):                # type: (...) -> Tuple[List[Job], int]
        """
        Finds all jobs in database matching search filters.
        """
        raise NotImplementedError

    def clear_jobs(self, request=None):
        # type: (Optional[Request]) -> bool
        """
        Removes all jobs from storage.
        """
        raise NotImplementedError


class QuoteStore(StoreInterface):
    """
    Storage for quotes.
    """
    type = 'quotes'

    def save_quote(self, quote):
        # type: (Quote) -> Quote
        """
        Stores a quote in storage.
        """
        raise NotImplementedError

    def fetch_by_id(self, quote_id):
        # type: (AnyStr) -> Quote
        """
        Get quote for given ``quote_id`` from storage.
        """
        raise NotImplementedError

    def list_quotes(self):
        # type: (...) -> List[Quote]
        """
        Lists all quotes in database.
        """
        raise NotImplementedError

    def find_quotes(self, process_id=None, page=0, limit=10, sort=None):
        # type: (Optional[AnyStr], Optional[int], Optional[int], Optional[AnyStr]) -> List[Quote]
        """
        Finds all quotes in database matching search filters.
        """
        raise NotImplementedError


class BillStore(StoreInterface):
    """
    Storage for bills.
    """
    type = 'bills'

    def save_bill(self, bill):
        # type: (Bill) -> List[Bill]
        """
        Stores a bill in storage.
        """
        raise NotImplementedError

    def fetch_by_id(self, bill_id):
        # type: (AnyStr) -> List[Bill]
        """
        Get bill for given ``bill_id`` from storage.
        """
        raise NotImplementedError

    def list_bills(self):
        # type: (...) -> List[Bill]
        """
        Lists all bills in database.
        """
        raise NotImplementedError

    def find_bills(self, quote_id=None, page=0, limit=10, sort=None):
        # type: (Optional[AnyStr], Optional[int], Optional[int], Optional[AnyStr]) -> List[Bill]
        """
        Finds all bills in database matching search filters.
        """
        raise NotImplementedError
