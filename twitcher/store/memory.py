"""
Read or write data from or to local memory.

Though not very valuable in a production setup, these store adapters are great
for testing purposes.
"""

import six
from twitcher.store.base import (
    AccessTokenStore,
    ServiceStore,
    ProcessStore,
    JobStore,
    QuoteStore,
    BillStore,
)
from twitcher.exceptions import (
    AccessTokenNotFound,
    ServiceRegistrationError,
    ServiceNotFound,
    ProcessNotAccessible,
    ProcessNotFound,
    JobNotFound,
)
from twitcher.datatype import Service, Process, Job
from twitcher import namesgenerator
from twitcher.utils import baseurl
from twitcher.visibility import visibility_values


class MemoryStore(object):
    def __init__(self, *args, **kwargs):
        self.store = {}


class MemoryTokenStore(AccessTokenStore, MemoryStore):
    """
    Stores tokens in memory.
    Useful for testing purposes or APIs with a very limited set of clients.

    Use mongodb as storage to be able to scale.
    """
    def __init__(self, *args, **kwargs):
        AccessTokenStore.__init__(self)
        MemoryStore.__init__(self, *args, **kwargs)

    def save_token(self, access_token):
        self.store[access_token.token] = access_token
        return True

    def delete_token(self, token):
        if token in self.store:
            del self.store[token]

    def fetch_by_token(self, token):
        if token not in self.store:
            raise AccessTokenNotFound

        return self.store[token]

    def clear_tokens(self):
        self.store = {}


class MemoryServiceStore(ServiceStore, MemoryStore):
    """
    Stores OWS services in memory. Useful for testing purposes.
    """
    def __init__(self, *args, **kwargs):
        ServiceStore.__init__(self)
        MemoryStore.__init__(self, *args, **kwargs)
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


class MemoryProcessStore(ProcessStore, MemoryStore):
    """
    Stores WPS processes in memory. Useful for testing purposes.
    """

    def __init__(self, *args, **kwargs):
        ProcessStore.__init__(self)
        MemoryStore.__init__(self, *args, **kwargs)
        default_processes = kwargs.get('default_processes')
        self.sane_name_config = {'assert_invalid': False, 'replace_invalid': True}
        if isinstance(default_processes, list):
            for process in default_processes:
                self.save_process(process)

    def save_process(self, process, overwrite=True, request=None):
        """
        Stores a WPS process in storage.

        :param process: An instance of :class:`twitcher.datatype.Process`.
        :param overwrite: Overwrite the process by name if existing.
        :param request:
        """
        sane_name = namesgenerator.get_sane_name(process.identifier, **self.sane_name_config)
        if not self.store.get(sane_name) or overwrite:
            if not process.title:
                process['title'] = sane_name
            self.store[sane_name] = Process(process)
        return self.fetch_by_id(sane_name)

    def delete_process(self, process_id, visibility=None, request=None):
        """
        Removes process from database, optionally filtered by visibility.
        """
        sane_name = namesgenerator.get_sane_name(process_id, **self.sane_name_config)
        if self.fetch_by_id(sane_name, visibility=visibility, request=request):
            del self.store[sane_name]

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
        return [process.identifier for process in self.store if process.visibility in visibility]

    def fetch_by_id(self, process_id, visibility=None, request=None):
        """
        Get process for given ``name`` from storage, optionally filtered by visibility.

        :return: An instance of :class:`twitcher.datatype.Process`.
        """
        sane_name = namesgenerator.get_sane_name(process_id, **self.sane_name_config)
        process = self.store.get(sane_name)
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
        self.store = {}
        return True


class MemoryJobStore(JobStore, MemoryStore):
    """
    Stores job tracking in memory. Useful for testing purposes.
    """

    def __init__(self, *args, **kwargs):
        JobStore.__init__(self)
        MemoryStore.__init__(self, *args, **kwargs)

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
        return self.update_job(job)

    def update_job(self, job):
        """
        Updates a job parameters in mongodb storage.
        :param job: instance of ``twitcher.datatype.Job``.
        """
        if not isinstance(job, Job):
            raise TypeError("Not a valid `twitcher.datatype.Job`.")
        self.store[job.id] = job
        return self.store[job.id]

    def delete_job(self, job_id, request=None):
        """
        Removes job from memory.
        """
        job = self.fetch_by_id(job_id, request)
        del self.store[job.id]

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
        jobs = self.store.values()
        return jobs, len(jobs)

    def find_jobs(self, request, page=0, limit=10, process=None, service=None,
                  tags=None, access=None, status=None, sort=None):
        """
        Finds all jobs in memory matching search filters.
        """
        # FIXME: validate inputs before filtering, sorting and paging
        jobs, count = self.list_jobs(request=request)
        jobs = filter(lambda j: j.process == process or process is None, jobs)
        jobs = filter(lambda j: j.service == service or service is None, jobs)
        jobs = filter(lambda j: j.access == access or access is None, jobs)
        jobs = filter(lambda j: j.status == status or status is None, jobs)
        jobs = filter(lambda j: all(t in j.tags for t in tags) if tags else True, jobs)
        jobs = sorted(jobs, key=lambda j: j.get(sort) if sort else j.id)
        jobs = [jobs[i:i+limit] for i in range(0, len(jobs), limit)]
        return jobs[page]

    def clear_jobs(self, request=None):
        """
        Removes all jobs from memory.
        """
        self.__init__()


class MemoryQuoteStore(QuoteStore, MemoryStore):
    """
    Storage for quotes in memory.
    """

    def __init__(self, *args, **kwargs):
        QuoteStore.__init__(self)
        MemoryStore.__init__(self, *args, **kwargs)

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


class MemoryBillStore(BillStore, MemoryStore):
    """
    Storage for bills in memory.
    """

    def __init__(self, *args, **kwargs):
        BillStore.__init__(self)
        MemoryStore.__init__(self, *args, **kwargs)

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
