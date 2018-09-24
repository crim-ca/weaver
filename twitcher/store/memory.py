"""
Read or write data from or to local memory.

Though not very valuable in a production setup, these store adapters are great
for testing purposes.
"""

from twitcher.store.base import AccessTokenStore
from twitcher.exceptions import AccessTokenNotFound


class MemoryTokenStore(AccessTokenStore):
    """
    Stores tokens in memory.
    Useful for testing purposes or APIs with a very limited set of clients.

    Use mongodb as storage to be able to scale.
    """
    def __init__(self):
        self.access_tokens = {}

    def save_token(self, access_token):
        self.access_tokens[access_token.token] = access_token
        return True

    def delete_token(self, token):
        if token in self.access_tokens:
            del self.access_tokens[token]

    def fetch_by_token(self, token):
        if token not in self.access_tokens:
            raise AccessTokenNotFound

        return self.access_tokens[token]

    def clear_tokens(self):
        self.access_tokens = {}


from twitcher.store.base import ServiceStore
from twitcher.datatype import Service
from twitcher.exceptions import ServiceRegistrationError, ServiceNotFound
from twitcher import namesgenerator
from twitcher.utils import baseurl


class MemoryServiceStore(ServiceStore):
    """
    Stores OWS services in memory. Useful for testing purposes.
    """
    def __init__(self):
        self.url_index = {}
        self.name_index = {}

    def _delete(self, url=None, name=None):
        if url:
            service = self.url_index[url]
            del self.name_index[service['name']]
            del self.url_index[url]
        elif name:
            service = self.name_index[name]
            del self.url_index[service['url']]
            del self.name_index[name]

    def _insert(self, service):
        self.name_index[service['name']] = service
        self.url_index[service['url']] = service

    def save_service(self, service, overwrite=True, request=None):
        """
        Store an OWS service in database.
        """

        service_url = baseurl(service.url)
        # check if service is already registered
        if service_url in self.url_index:
            if overwrite:
                self._delete(url=service_url)
            else:
                raise ServiceRegistrationError("service url already registered.")

        name = namesgenerator.get_sane_name(service.name)
        if not name:
            name = namesgenerator.get_random_name()
            if name in self.name_index:
                name = namesgenerator.get_random_name(retry=True)
        if name in self.name_index:
            if overwrite:
                self._delete(name=name)
            else:
                raise Exception("service name already registered.")
        self._insert(Service(
            url=service_url,
            name=name,
            type=service.type,
            public=service.public,
            auth=service.auth))
        return self.fetch_by_url(url=service_url, request=request)

    def delete_service(self, name, request=None):
        """
        Removes service from registry database.
        """
        self._delete(name=name)
        return True

    def list_services(self, request=None):
        """
        Lists all services in memory storage.
        """
        my_services = []
        for service in self.url_index.values():
            my_services.append(Service(service))
        return my_services

    def fetch_by_name(self, name, request=None):
        """
        Get service for given ``name`` from memory storage.
        """
        service = self.name_index.get(name)
        if not service:
            raise ServiceNotFound
        return Service(service)

    def fetch_by_url(self, url, request=None):
        """
        Get service for given ``url`` from memory storage.
        """
        service = self.url_index.get(baseurl(url))
        if not service:
            raise ServiceNotFound
        return Service(service)

    def clear_services(self, request=None):
        """
        Removes all OWS services from memory storage.
        """
        self.url_index = {}
        self.name_index = {}
        return True


from twitcher.store.base import ProcessStore


class MemoryProcessStore(ProcessStore):
    """
    Stores WPS processes in memory. Useful for testing purposes.
    """

    def __init__(self, init_processes=None):
        self.name_index = {}
        if isinstance(init_processes, list):
            for process in init_processes:
                self.save_process(process)

    def save_process(self, process, overwrite=True, request=None):
        """
        Stores a WPS process in storage.

        :param process: An instance of :class:`twitcher.datatype.Process`.
        """
        sane_name = namesgenerator.get_sane_name(process.title)
        if not self.name_index.get(sane_name) or overwrite:
            process.title = sane_name
            self.name_index[sane_name] = process

    def delete_process(self, name, request=None):
        """
        Removes process from database.
        """
        sane_name = namesgenerator.get_sane_name(name)
        if self.name_index.get(sane_name):
            del self.name_index[sane_name]

    def list_processes(self, request=None):
        """
        Lists all processes in database.
        """
        return [process.title for process in self.name_index]

    def fetch_by_id(self, process_id, request=None):
        """
        Get process for given ``name`` from storage.

        :return: An instance of :class:`twitcher.datatype.Process`.
        """
        sane_name = namesgenerator.get_sane_name(process_id)
        process = self.name_index.get(sane_name)
        return process


from twitcher.store.base import JobStore


class MemoryJobStore(JobStore):
    """
    Stores job tracking in memory. Useful for testing purposes.
    """
    def save_job(self, task_id, process, service=None, is_workflow=False, user_id=None, async=True, custom_tags=[]):
        """
        Stores a job in memory.
        """
        raise NotImplementedError

    def update_job(self, job):
        """
        Updates a job parameters in mongodb storage.
        :param job: instance of ``twitcher.datatype.Job``.
        """
        raise NotImplementedError

    def delete_job(self, job_id, request=None):
        """
        Removes job from memory.
        """
        raise NotImplementedError

    def fetch_by_id(self, job_id, request=None):
        """
        Gets job for given ``job_id`` from memory.
        """
        raise NotImplementedError

    def list_jobs(self, request=None):
        """
        Lists all jobs in memory.
        """
        raise NotImplementedError

    def find_jobs(self, request, page=0, limit=10, process=None, service=None,
                  tags=None, access=None, status=None, sort=None):
        """
        Finds all jobs in memory matching search filters.
        """
        raise NotImplementedError

    def clear_jobs(self, request=None):
        """
        Removes all jobs from memory.
        """
        raise NotImplementedError


class MemoryQuoteStore(object):
    """
    Storage for quotes in memory.
    """

    def save_quote(self, quote):
        """
        Stores a quote in memory.
        """
        raise NotImplementedError

    def fetch_by_id(self, quote_id):
        """
        Get quote for given ``quote_id`` from memory.
        """
        raise NotImplementedError

    def list_quotes(self):
        """
        Lists all quotes in memory.
        """
        raise NotImplementedError

    def find_quotes(self, process_id=None, page=0, limit=10, sort=None):
        """
        Finds all quotes in memory matching search filters.
        """
        raise NotImplementedError


class MemoryBillStore(object):
    """
    Storage for bills in memory.
    """

    def save_bill(self, bill):
        """
        Stores a bill in memory.
        """
        raise NotImplementedError

    def fetch_by_id(self, bill_id):
        """
        Get bill for given ``bill_id`` from memory.
        """
        raise NotImplementedError

    def list_bills(self):
        """
        Lists all bills in memory.
        """
        raise NotImplementedError

    def find_bills(self, quote_id=None, page=0, limit=10, sort=None):
        """
        Finds all bills in memory matching search filters.
        """
        raise NotImplementedError
