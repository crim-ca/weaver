"""
Store adapters to read/write data to from/to mongodb using pymongo.
"""
import pymongo

from twitcher.store.base import AccessTokenStore
from twitcher.datatype import AccessToken
from twitcher.exceptions import AccessTokenNotFound
from twitcher.utils import islambda
from twitcher.sort import *
from twitcher.status import *
from pyramid.security import authenticated_userid
from pymongo import ASCENDING, DESCENDING
from datetime import datetime
import six

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
from twitcher.visibility import visibility_values
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

    def save_process(self, process, overwrite=False, request=None):
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

    def list_processes(self, visibility=None, request=None):
        """
        Lists all processes in database, optionally filtered by visibility.

        :param visibility: One value amongst `twitcher.visibility`.
        """
        db_processes = []
        search_filters = {}
        if visibility is None:
            visibility = visibility_values
        if isinstance(visibility, six.string_types):
            visibility = [visibility]
        for v in visibility:
            if v not in visibility_values:
                raise ValueError("Invalid visibility value `{0!s}` is not one of {1!s}"
                                 .format(v, list(visibility_values)))
        search_filters['visibility'] = {'$in': visibility}
        for process in self.collection.find(search_filters).sort('identifier', pymongo.ASCENDING):
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
        :raises: TypeError or ValueError in case of invalid parameter.
        """
        process = self.fetch_by_id(process_id)
        process.visibility = visibility
        self.save_process(process, overwrite=True)


from twitcher.store.base import JobStore
from twitcher.datatype import Job
from twitcher.exceptions import JobRegistrationError, JobNotFound, JobUpdateError


class MongodbJobStore(JobStore, MongodbStore):
    """
    Registry for OWS service process jobs tracking. Uses mongodb to store job attributes.
    """

    def save_job(self, task_id, process, service=None, is_workflow=False, user_id=None, async=True, custom_tags=[]):
        """
        Stores a job in mongodb.
        """
        try:
            tags = ['dev']
            tags.extend(custom_tags)
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
        except Exception as ex:
            raise JobRegistrationError("Error occurred during job registration: [{}]".format(repr(ex)))
        if job is None:
            raise JobRegistrationError("Failed to retrieve registered job.")
        return job

    def update_job(self, job):
        """
        Updates a job parameters in mongodb storage.
        :param job: instance of ``twitcher.datatype.Job``.
        """
        try:
            result = self.collection.update_one({'task_id': job.task_id}, {'$set': job.params})
            if result.acknowledged and result.modified_count == 1:
                return self.fetch_by_id(job.task_id)
        except Exception as ex:
            raise JobUpdateError("Error occurred during job update: [{}]".format(repr(ex)))
        raise JobUpdateError("Failed to update specified job: `{}`".format(str(job)))

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
            raise JobNotFound("Could not find job matching: `{}`".format(job_id))
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
                  tags=None, access=None, status=None, sort=None):
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
            if tags is not None:
                search_filters['tags'] = {'$all': tags}
            search_filters['user_id'] = authenticated_userid(request)

        if status in job_status_categories.keys():
            search_filters['status'] = {'$in': job_status_categories[status]}
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
        if sort not in job_sort_values:
            raise JobNotFound("Invalid sorting method: `{}`".format(repr(sort)))

        sort_order = DESCENDING if sort == SORT_FINISHED or sort == SORT_CREATED else ASCENDING
        sort_criteria = [(sort, sort_order)]
        found = self.collection.find(search_filters)
        count = found.count()
        items = [Job(item) for item in list(found.skip(page * limit).limit(limit).sort(sort_criteria))]
        return items, count

    def clear_jobs(self, request=None):
        """
        Removes all jobs from mongodb storage.
        """
        self.collection.drop()
        return True


from twitcher.store.base import QuoteStore
from twitcher.datatype import Quote
from twitcher.exceptions import QuoteRegistrationError, QuoteNotFound, QuoteInstanceError


class MongodbQuoteStore(QuoteStore, MongodbStore):
    """
    Registry for quotes. Uses mongodb to store quote attributes.
    """

    def save_quote(self, quote):
        """
        Stores a quote in mongodb.
        """
        if not isinstance(quote, Quote):
            raise QuoteInstanceError("Invalid quote object: `{}`".format(repr(quote)))
        try:
            self.collection.insert_one(quote)
            quote = self.fetch_by_id(quote_id=quote.id)
        except Exception as ex:
            raise QuoteRegistrationError("Error occurred during quote registration: [{}]".format(repr(ex)))
        if quote is None:
            raise QuoteRegistrationError("Failed to retrieve registered quote.")
        return quote

    def fetch_by_id(self, quote_id):
        """
        Gets quote for given ``quote_id`` from mongodb storage.
        """
        quote = self.collection.find_one({'id': quote_id})
        if not quote:
            raise QuoteNotFound("Could not find quote matching: `{}`".format(quote_id))
        return Quote(quote)

    def list_quotes(self):
        """
        Lists all quotes in mongodb storage.
        """
        quotes = []
        for quote in self.collection.find().sort('id', ASCENDING):
            quotes.append(Quote(quote))
        return quotes

    def find_quotes(self, process_id=None, page=0, limit=10, sort=None):
        """
        Finds all quotes in mongodb storage matching search filters.
        """
        search_filters = {}

        if isinstance(process_id, six.string_types):
            search_filters['process'] = process_id

        if sort is None:
            sort = SORT_ID
        if sort not in quote_sort_values:
            raise QuoteNotFound("Invalid sorting method: `{}`".format(repr(sort)))

        sort_order = ASCENDING
        sort_criteria = [(sort, sort_order)]
        found = self.collection.find(search_filters)
        count = found.count()
        items = [Quote(item) for item in list(found.skip(page * limit).limit(limit).sort(sort_criteria))]
        return items, count


from twitcher.store.base import BillStore
from twitcher.datatype import Bill
from twitcher.exceptions import BillRegistrationError, BillNotFound, BillInstanceError


class MongodbBillStore(BillStore, MongodbStore):
    """
    Registry for bills. Uses mongodb to store bill attributes.
    """

    def save_bill(self, bill):
        """
        Stores a bill in mongodb.
        """
        if not isinstance(bill, Bill):
            raise BillInstanceError("Invalid bill object: `{}`".format(repr(bill)))
        try:
            self.collection.insert_one(bill)
            bill = self.fetch_by_id(bill_id=bill.id)
        except Exception as ex:
            raise BillRegistrationError("Error occurred during bill registration: [{}]".format(repr(ex)))
        if bill is None:
            raise BillRegistrationError("Failed to retrieve registered bill.")
        return bill

    def fetch_by_id(self, bill_id):
        """
        Gets bill for given ``bill_id`` from mongodb storage.
        """
        bill = self.collection.find_one({'id': bill_id})
        if not bill:
            raise BillNotFound("Could not find bill matching: `{}`".format(bill_id))
        return Bill(bill)

    def list_bills(self):
        """
        Lists all bills in mongodb storage.
        """
        bills = []
        for bill in self.collection.find().sort('id', ASCENDING):
            bills.append(Bill(bill))
        return bills

    def find_bills(self, quote_id=None, page=0, limit=10, sort=None):
        """
        Finds all bills in mongodb storage matching search filters.
        """
        search_filters = {}

        if isinstance(quote_id, six.string_types):
            search_filters['quote'] = quote_id

        if sort is None:
            sort = SORT_ID
        if sort not in bill_sort_values:
            raise BillNotFound("Invalid sorting method: `{}`".format(repr(sort)))

        sort_order = ASCENDING
        sort_criteria = [(sort, sort_order)]
        found = self.collection.find(search_filters)
        count = found.count()
        items = [Bill(item) for item in list(found.skip(page * limit).limit(limit).sort(sort_criteria))]
        return items, count
