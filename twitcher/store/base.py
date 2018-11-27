"""
Store adapters to persist and retrieve data during the twitcher process or
for later use. For example an access token storage and a service registry.

This module provides base classes that can be extended to implement your own
solution specific to your needs.

The implementation is based on `python-oauth2 <http://python-oauth2.readthedocs.io/en/latest/>`_.
"""
from pyramid.request import Request
from typing import Any, Optional, List
from twitcher.datatype import Job, Service, Process, Quote, Bill, AccessToken


class AccessTokenStore(object):

    def save_token(self, access_token):
        # type: (AccessToken) -> None
        """
        Stores an access token with additional data.
        """
        raise NotImplementedError

    def delete_token(self, token):
        # type: (str) -> None
        """
        Deletes an access token from the store using its token string to identify it.
        This invalidates both the access token and the token.
        """
        raise NotImplementedError

    def fetch_by_token(self, token):
        # type: (str) -> AccessToken
        """
        Fetches an access token from the store using its token string to identify it.
        """
        raise NotImplementedError

    def clear_tokens(self):
        # type: (...) -> None
        """
        Removes all tokens from database.
        """
        raise NotImplementedError


class ServiceStore(object):
    """
    Storage for OWS services.
    """

    def save_service(self, service, overwrite=True, request=None):
        # type: (Service, Optional[bool], Optional[Request]) -> Service
        """
        Stores an OWS service in storage.
        """
        raise NotImplementedError

    def delete_service(self, name, request=None):
        # type: (str, Optional[Request]) -> bool
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

    def fetch_by_name(self, name, request=None):
        # type: (str, Optional[Request]) -> Service
        """
        Get service for given ``name`` from storage.
        """
        raise NotImplementedError

    def fetch_by_url(self, url, request=None):
        # type: (str, Optional[Request]) -> Service
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


class ProcessStore(object):
    """
    Storage for local WPS processes.
    """

    def save_process(self, process, overwrite=True, request=None):
        # type: (Process, Optional[bool], Optional[Request]) -> Process
        """
        Stores a WPS process in storage.
        """
        raise NotImplementedError

    def delete_process(self, process_id, request=None):
        # type: (str, Optional[Request]) -> bool
        """
        Removes process from database.
        """
        raise NotImplementedError

    def list_processes(self, visibility=None, request=None):
        # type: (Optional[str], Optional[Request]) -> List[Process]
        """
        Lists all processes in database, optionally filtered by visibility.

        :param visibility: One value amongst `twitcher.visibility`.
        :param request:
        """
        raise NotImplementedError

    def fetch_by_id(self, process_id, request=None):
        # type: (str, Optional[Request]) -> Process
        """
        Get process for given ``name`` from storage.

        :return: An instance of :class:`twitcher.datatype.Process`.
        """
        raise NotImplementedError

    def get_visibility(self, process_id, request=None):
        # type: (str, Optional[Request]) -> str
        """
        Get visibility of a process.

        :return: One value amongst `twitcher.visibility`.
        """
        raise NotImplementedError

    def set_visibility(self, process_id, visibility, request=None):
        # type: (str, str, Optional[Request]) -> None
        """
        Set visibility of a process.

        :param visibility: One value amongst `twitcher.visibility`.
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


class JobStore(object):
    """
    Storage for job tracking.
    """

    def save_job(self,
                 task_id,               # type: str
                 process,               # type: str
                 service=None,          # type: Optional[str]
                 inputs=None,           # type: Optional[List[Any]]
                 is_workflow=False,     # type: Optional[bool]
                 user_id=None,          # type: Optional[int]
                 execute_async=True,    # type: Optional[bool]
                 custom_tags=None       # type: Optional[List[str]]
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
        # type: (str, Optional[Request]) -> bool
        """
        Removes job from database.
        """
        raise NotImplementedError

    def fetch_by_id(self, job_id, request=None):
        # type: (str, Optional[Request]) -> Job
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
                  process=None,     # type: Optional[str]
                  service=None,     # type: Optional[str]
                  tags=None,        # type: Optional[List[str]]
                  access=None,      # type: Optional[str]
                  status=None,      # type: Optional[str]
                  sort=None,        # type: Optional[str]
                  ):                # type: (...) -> List[Job]
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


class QuoteStore(object):
    """
    Storage for quotes.
    """

    def save_quote(self, quote):
        # type: (Quote) -> Quote
        """
        Stores a quote in storage.
        """
        raise NotImplementedError

    def fetch_by_id(self, quote_id):
        # type: (str) -> Quote
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
        # type: (Optional[str], Optional[int], Optional[int], Optional[str]) -> List[Quote]
        """
        Finds all quotes in database matching search filters.
        """
        raise NotImplementedError


class BillStore(object):
    """
    Storage for bills.
    """

    def save_bill(self, bill):
        # type: (Bill) -> List[Bill]
        """
        Stores a bill in storage.
        """
        raise NotImplementedError

    def fetch_by_id(self, bill_id):
        # type: (str) -> List[Bill]
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
        # type: (Optional[str], Optional[int], Optional[int], Optional[str]) -> List[Bill]
        """
        Finds all bills in database matching search filters.
        """
        raise NotImplementedError
