"""
Read or write data from or to local memory.

Though not very valuable in a production setup, these store adapters are great
for testing purposes.
"""

import six
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
        self.sane_name_config = {'assert_invalid': False, 'replace_invalid': True}

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

        name = namesgenerator.get_sane_name(service.name, **self.sane_name_config)
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
from twitcher.exceptions import ProcessNotAccessible, ProcessNotFound
from twitcher.visibility import visibility_values
from twitcher.datatype import Process


class MemoryProcessStore(ProcessStore):
    """
    Stores WPS processes in memory. Useful for testing purposes.
    """

    def __init__(self, init_processes=None):
        self.name_index = {}
        self.sane_name_config = {'assert_invalid': False, 'replace_invalid': True}
        if isinstance(init_processes, list):
            for process in init_processes:
                self.save_process(process)

    def save_process(self, process, overwrite=True, request=None):
        """
        Stores a WPS process in storage.

        :param process: An instance of :class:`twitcher.datatype.Process`.
        :param overwrite: Overwrite the process by name if existing.
        :param request:
        """
        sane_name = namesgenerator.get_sane_name(process.identifier, **self.sane_name_config)
        if not self.name_index.get(sane_name) or overwrite:
            if not process.title:
                process['title'] = sane_name
            self.name_index[sane_name] = Process(process)
        return self.fetch_by_id(sane_name)

    def delete_process(self, process_id, request=None):
        """
        Removes process from database.
        """
        sane_name = namesgenerator.get_sane_name(process_id, **self.sane_name_config)
        if self.name_index.get(sane_name):
            del self.name_index[sane_name]

    def list_processes(self, visibility=None, request=None):
        """
        Lists all processes in database, optionally filtered by visibility.

        :param visibility: One value amongst `twitcher.visibility`.
        :param request:
        """
        if visibility is None:
            visibility = list(visibility_values)
        if isinstance(visibility, six.string_types):
            visibility = [visibility]
        for v in visibility:
            if v not in visibility_values:
                raise ValueError("Invalid visibility value `{0!s}` is not one of {1!s}"
                                 .format(v, list(visibility_values)))
        return [process.identifier for process in self.name_index if process.visibility in visibility]

    def fetch_by_id(self, process_id, visibility=None, request=None):
        """
        Get process for given ``name`` from storage, optionally filtered by visibility.

        :return: An instance of :class:`twitcher.datatype.Process`.
        """
        sane_name = namesgenerator.get_sane_name(process_id, **self.sane_name_config)
        process = self.name_index.get(sane_name)
        if not process:
            raise ProcessNotFound("Process `{}` could not be found.".format(sane_name))
        process = Process(process)
        if visibility is not None and process.visibility != visibility:
            raise ProcessNotAccessible("Process `{}` cannot be accessed.".format(sane_name))
        return process

    def get_visibility(self, process_id, request=None):
        """
        Get visibility of a process.

        :return: One value amongst `twitcher.visibility`.
        """
        process = self.fetch_by_id(process_id)
        return process.visibility

    def set_visibility(self, process_id, visibility, request=None):
        """
        Set visibility of a process.

        :param visibility: One value amongst `twitcher.visibility`.
        :param process_id:
        :param request:
        :raises: TypeError or ValueError in case of invalid parameter.
        """
        process = self.fetch_by_id(process_id)
        process.visibility = visibility
        self.save_process(process)

    def clear_processes(self, request=None):
        """
        Clears all processes from the store.
        """
        self.name_index = {}
        return True


from twitcher.datatype import Job
from twitcher.store.base import JobStore
from twitcher.exceptions import JobNotFound


class MemoryJobStore(JobStore):
    """
    Stores job tracking in memory. Useful for testing purposes.
    """
    store = None

    def __init__(self):
        self.store = {}

    def save_job(self, task_id, process, service=None, inputs=None,
                 is_workflow=False, user_id=None, execute_async=True, custom_tags=None):
        """
        Stores a job in memory.
        """
        job = Job({
            'task_id': task_id,
            'process': process,
            'service': service,
            'inputs': inputs,
            'is_workflow': is_workflow,
            'user_id': user_id,
            'execute_async': execute_async,
            'custom_tags': [] if not custom_tags else custom_tags,
        })
        self.store[job.id] = job

    def update_job(self, job):
        """
        Updates a job parameters in mongodb storage.
        :param job: instance of ``twitcher.datatype.Job``.
        """
        self.store[job.id] = job

    def delete_job(self, job_id, request=None):
        """
        Removes job from memory.
        """
        del self.store[job_id]

    def fetch_by_id(self, job_id, request=None):
        """
        Gets job for given ``job_id`` from memory.
        """
        job = self.store.get(job_id)
        if job is None:
            raise JobNotFound
        return job

    def list_jobs(self, request=None):
        """
        Lists all jobs in memory.
        """
        return self.store

    def find_jobs(self, request, page=0, limit=10, process=None, service=None,
                  tags=None, access=None, status=None, sort=None):
        """
        Finds all jobs in memory matching search filters.
        """
        return {}, 0

    def clear_jobs(self, request=None):
        """
        Removes all jobs from memory.
        """
        self.__init__()


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
