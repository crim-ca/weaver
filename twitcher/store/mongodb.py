"""
Store adapters to read/write data to from/to mongodb using pymongo.
"""
import pymongo

from twitcher.store.base import AccessTokenStore
from twitcher.datatype import AccessToken
from twitcher.exceptions import AccessTokenNotFound
from twitcher.utils import islambda
from twitcher.wps_restapi.utils import wps_restapi_base_url

import logging
LOGGER = logging.getLogger(__name__)


class MongodbStore(object):
    """
    Base class extended by all concrete store adapters.
    """

    def __init__(self, collection):
        self.collection = collection


class MongodbTokenStore(AccessTokenStore, MongodbStore):
    def save_token(self, access_token):
        self.collection.insert_one(access_token)

    def delete_token(self, token):
        self.collection.delete_one({'token': token})

    def fetch_by_token(self, token):
        token = self.collection.find_one({'token': token})
        if not token:
            raise AccessTokenNotFound
        return AccessToken(token)

    def clear_tokens(self):
        self.collection.drop()


from twitcher.store.base import ServiceStore
from twitcher.datatype import Service
from twitcher.exceptions import ServiceRegistrationError, ServiceNotFound
from twitcher import namesgenerator
from twitcher.utils import baseurl


class MongodbServiceStore(ServiceStore, MongodbStore):
    """
    Registry for OWS services. Uses mongodb to store service url and attributes.
    """

    def save_service(self, service, overwrite=True, request=None):
        """
        Stores an OWS service in mongodb.
        """

        service_url = baseurl(service.url)
        # check if service is already registered
        if self.collection.count({'url': service_url}) > 0:
            if overwrite:
                self.collection.delete_one({'url': service_url})
            else:
                raise ServiceRegistrationError("service url already registered.")

        name = namesgenerator.get_sane_name(service.name)
        if not name:
            name = namesgenerator.get_random_name()
            if self.collection.count({'name': name}) > 0:
                name = namesgenerator.get_random_name(retry=True)
        if self.collection.count({'name': name}) > 0:
            if overwrite:
                self.collection.delete_one({'name': name})
            else:
                raise Exception("service name already registered.")
        self.collection.insert_one(Service(
            url=service_url,
            name=name,
            type=service.type,
            public=service.public,
            auth=service.auth))
        return self.fetch_by_url(url=service_url, request=request)

    def delete_service(self, name, request=None):
        """
        Removes service from mongodb storage.
        """
        self.collection.delete_one({'name': name})
        return True

    def list_services(self, request=None):
        """
        Lists all services in mongodb storage.
        """
        my_services = []
        for service in self.collection.find().sort('name', pymongo.ASCENDING):
            my_services.append(Service(service))
        return my_services

    def fetch_by_name(self, name, request=None):
        """
        Gets service for given ``name`` from mongodb storage.
        """
        service = self.collection.find_one({'name': name})
        if not service:
            raise ServiceNotFound
        return Service(service)

    def fetch_by_url(self, url, request=None):
        """
        Gets service for given ``url`` from mongodb storage.
        """
        service = self.collection.find_one({'url': baseurl(url)})
        if not service:
            raise ServiceNotFound
        return Service(service)

    def clear_services(self, request=None):
        """
        Removes all OWS services from mongodb storage.
        """
        self.collection.drop()
        return True


from twitcher.store.base import ProcessStore
from twitcher.exceptions import ProcessNotFound, ProcessRegistrationError, ProcessInstanceError
from twitcher.datatype import Process as ProcessDB
from pywps import Process as ProcessWPS


class MongodbProcessStore(ProcessStore, MongodbStore):
    """
    Registry for WPS processes. Uses mongodb to store processes and attributes.
    """

    def __init__(self, collection, settings, default_processes=None):
        super(MongodbProcessStore, self).__init__(collection=collection)
        self.default_host = settings.get('twitcher.url')
        self.default_wps_endpoint = '{host}{wps}'.format(host=self.default_host, wps=settings.get('twitcher.wps_path'))
        if default_processes:
            registered_processes = [process.identifier for process in self.list_processes()]
            for process in default_processes:
                sane_name = self._get_process_id(process)
                if sane_name not in registered_processes:
                    self._add_process(process)

    def _add_process(self, process):
        if isinstance(process, ProcessWPS):
            new_process = ProcessDB.from_wps(process, executeEndpoint=self.default_wps_endpoint)
        else:
            new_process = process
        if not isinstance(new_process, ProcessDB):
            raise ProcessInstanceError("Unsupported process type `{}`".format(type(process)))

        new_process['type'] = self._get_process_type(process)
        new_process['identifier'] = self._get_process_id(process)
        new_process['executeEndpoint'] = self._get_process_url(process)
        self.collection.insert_one(new_process)

    @staticmethod
    def _get_process_field(process, function_dict):
        """
        Takes a lambda expression or a dict of process-specific lambda expressions to retrieve a field.
        Validates that the passed process object is one of the supported types.

        :param process: process to retrieve the field from.
        :param function_dict: lambda or dict of lambda of process type
        :return: retrieved field if the type was supported
        :raises: ProcessInstanceError on invalid process type
        """
        if isinstance(process, ProcessDB):
            if islambda(function_dict):
                return function_dict()
            return function_dict[ProcessDB]()
        elif isinstance(process, ProcessWPS):
            if islambda(function_dict):
                return function_dict()
            return function_dict[ProcessWPS]()
        else:
            raise ProcessInstanceError("Unsupported process type `{}`".format(type(process)))

    def _get_process_id(self, process):
        return self._get_process_field(process, lambda: process.identifier)

    def _get_process_type(self, process):
        return self._get_process_field(process, {ProcessDB: lambda: process.type, ProcessWPS: lambda: 'wps'}).lower()

    def _get_process_url(self, process):
        url = self._get_process_field(process, {ProcessDB: lambda: process.executeEndpoint, ProcessWPS: lambda: None})
        if not url:
            url = self.default_wps_endpoint
        return url

    def save_process(self, process, overwrite=True, request=None):
        """
        Stores a WPS process in storage.

        :param process: An instance of :class:`twitcher.datatype.Process`.
        :param overwrite: Overwrite the matching process instance by name if conflicting.
        :param request: <unused>
        """
        sane_name = self._get_process_id(process)
        if self.collection.count({'identifier': sane_name}) > 0:
            if overwrite:
                self.collection.delete_one({'identifier': sane_name})
            else:
                raise ProcessRegistrationError("Process `{}` already registered.".format(sane_name))
        self._add_process(process)
        return self.fetch_by_id(sane_name)

    def delete_process(self, process_id, request=None):
        """
        Removes process from database.
        """
        sane_name = namesgenerator.get_sane_name(process_id)
        self.collection.delete_one({'identifier': sane_name})
        return True

    def list_processes(self, request=None):
        """
        Lists all processes in database.
        """
        db_processes = []
        for process in self.collection.find().sort('identifier', pymongo.ASCENDING):
            db_processes.append(ProcessDB(process))
        return db_processes

    def fetch_by_id(self, process_id, request=None):
        """
        Get process for given ``name`` from storage.

        :return: An instance of :class:`twitcher.datatype.Process`.
        """
        sane_name = namesgenerator.get_sane_name(process_id)
        process = self.collection.find_one({'identifier': sane_name})
        if not process:
            raise ProcessNotFound("Process `{}` could not be found.".format(sane_name))
        return ProcessDB(process)


from twitcher.store.base import JobStore
from twitcher.datatype import Job
from twitcher.exceptions import JobRegistrationError, JobNotFound
from twitcher.wps_restapi.sort import *
from twitcher.wps_restapi.status import *
from pyramid.security import authenticated_userid
from pymongo import ASCENDING, DESCENDING
from datetime import datetime


class MongodbJobStore(JobStore, MongodbStore):
    """
    Registry for OWS service process jobs tracking. Uses mongodb to store job attributes.
    """

    def save_job(self, task_id, process, service=None, is_workflow=False, user_id=None, async=True):
        """
        Stores a job in mongodb.
        """
        try:
            tags = ['dev']
            if is_workflow:
                tags.append('workflow')
            else:
                tags.append('single')
            if async:
                tags.append('async')
            else:
                tags.append('sync')
            new_job = Job({
                'task_id': task_id,
                'user_id': user_id,
                'service': service,     # provider identifier (WPS service)
                'process': process,     # process identifier (WPS request)
                'status': STATUS_ACCEPTED,
                'is_workflow': is_workflow,
                'created': datetime.now(),
                'tags': tags,
            })
            self.collection.insert_one(new_job)
            job = self.fetch_by_id(job_id=task_id)
            if job is None:
                raise JobRegistrationError
            return job
        except Exception:
            raise JobRegistrationError

    def update_job(self, job):
        """
        Updates a job parameters in mongodb storage.
        :param job: instance of ``twitcher.datatype.Job``.
        """
        test = self.collection.update_one({'task_id': job.task_id}, {'$set': job.params})
        return self.fetch_by_id(job.task_id)

    def delete_job(self, job_id, request=None):
        """
        Removes job from mongodb storage.
        """
        self.collection.delete_one({'task_id': job_id})
        return True

    def fetch_by_id(self, job_id, request=None):
        """
        Gets job for given ``job_id`` from mongodb storage.
        """
        job = self.collection.find_one({'task_id': job_id})
        if not job:
            raise JobNotFound
        return Job(job)

    def list_jobs(self, request=None):
        """
        Lists all jobs in mongodb storage.
        """
        jobs = []
        for job in self.collection.find().sort('task_id', ASCENDING):
            jobs.append(Job(job))
        return jobs

    def find_jobs(self, request, page=0, limit=10, process=None, service=None,
                  tag=None, access=None, status=None, sort=None):
        """
        Finds all jobs in mongodb storage matching search filters.
        """
        search_filters = {}
        if access == 'public':
            search_filters['tags'] = 'public'
        elif access == 'private':
            search_filters['tags'] = {'$ne': 'public'}
            search_filters['user_id'] = authenticated_userid(request)
        elif access == 'all' and request.has_permission('admin'):
            pass
        else:
            if tag is not None:
                search_filters['tags'] = tag
            search_filters['user_id'] = authenticated_userid(request)

        if status in status_categories.keys():
            search_filters['status'] = {'$in': status_categories[status]}
        elif status:
            search_filters['status'] = status

        if process is not None:
            search_filters['process'] = process

        if service is not None:
            search_filters['service'] = service

        if sort is None:
            sort = SORT_CREATED
        elif sort == SORT_USER:
            sort = 'user_id'

        sort_order = DESCENDING if sort == SORT_FINISHED or sort == SORT_CREATED else ASCENDING
        sort_criteria = [(sort, sort_order)]
        found = self.collection.find(search_filters)
        count = found.count()
        items = list(found.skip(page * limit).limit(limit).sort(sort_criteria))
        return items, count

    def clear_jobs(self, request=None):
        """
        Removes all jobs from mongodb storage.
        """
        self.collection.drop()
        return True
