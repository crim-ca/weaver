"""
Store adapters to read/write data to from/to mongodb using pymongo.
"""
from twitcher.store.base import AccessTokenStore, ServiceStore, ProcessStore, JobStore, QuoteStore, BillStore
from twitcher.datatype import AccessToken, Service, Process as ProcessDB, Job, Quote, Bill
from twitcher.exceptions import AccessTokenNotFound
from twitcher.utils import islambda, now, baseurl
from twitcher.sort import *
from twitcher.status import STATUS_ACCEPTED, map_status, job_status_categories
from twitcher.visibility import visibility_values
from twitcher.exceptions import (
    ServiceRegistrationError, ServiceNotFound,
    ProcessNotAccessible, ProcessNotFound, ProcessRegistrationError, ProcessInstanceError,
    JobRegistrationError, JobNotFound, JobUpdateError,
    QuoteRegistrationError, QuoteNotFound, QuoteInstanceError,
    BillRegistrationError, BillNotFound, BillInstanceError,
)
from twitcher import namesgenerator
from twitcher.processes.types import PROCESS_WPS
# noinspection PyPackageRequirements
from pywps import Process as ProcessWPS
from pyramid.security import authenticated_userid
from pymongo import ASCENDING, DESCENDING
import pymongo
import six
import logging
LOGGER = logging.getLogger(__name__)


class MongodbStore(object):
    """
    Base class extended by all concrete store adapters.
    """

    def __init__(self, collection, sane_name_config=None):
        self.collection = collection
        self.sane_name_config = sane_name_config or {}


class MongodbTokenStore(AccessTokenStore, MongodbStore):
    """
    Registry for access tokens. Uses mongodb to store tokens and attributes.
    """

    def __init__(self, *args, **kwargs):
        AccessTokenStore.__init__(self)
        MongodbStore.__init__(self, *args, **kwargs)

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


class MongodbServiceStore(ServiceStore, MongodbStore):
    """
    Registry for OWS services. Uses mongodb to store service url and attributes.
    """

    def __init__(self, *args, **kwargs):
        ServiceStore.__init__(self)
        MongodbStore.__init__(self, *args, **kwargs)

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

        name = namesgenerator.get_sane_name(service.name, **self.sane_name_config)
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


class MongodbProcessStore(ProcessStore, MongodbStore):
    """
    Registry for WPS processes. Uses mongodb to store processes and attributes.
    """

    def __init__(self, *args, **kwargs):
        ProcessStore.__init__(self)
        MongodbStore.__init__(self, *args, **kwargs)
        settings = kwargs.get('settings', {})
        default_processes = kwargs.get('default_processes')
        self.default_host = settings.get('twitcher.url', '')
        self.default_wps_endpoint = '{host}{wps}'.format(host=self.default_host,
                                                         wps=settings.get('twitcher.wps_path', ''))
        if default_processes:
            registered_processes = [process.identifier for process in self.list_processes()]
            for process in default_processes:
                process_name = self._get_process_id(process)
                if process_name not in registered_processes:
                    self._add_process(process)

    def _add_process(self, process):
        if isinstance(process, ProcessWPS):
            new_process = ProcessDB.from_wps(process, processEndpointWPS1=self.default_wps_endpoint)
        else:
            new_process = process
        if not isinstance(new_process, ProcessDB):
            raise ProcessInstanceError("Unsupported process type `{}`".format(type(process)))

        # apply defaults if not specified
        new_process['type'] = self._get_process_type(process)
        new_process['identifier'] = self._get_process_id(process)
        new_process['processEndpointWPS1'] = self._get_process_endpoint_wps1(process)
        new_process['visibility'] = new_process.visibility
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
        return self._get_process_field(process, {ProcessDB: lambda: process.type,
                                                 ProcessWPS: lambda: getattr(process, 'type', PROCESS_WPS)}).lower()

    def _get_process_endpoint_wps1(self, process):
        url = self._get_process_field(process, {ProcessDB: lambda: process.processEndpointWPS1,
                                                ProcessWPS: lambda: None})
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
        process_id = self._get_process_id(process)
        sane_name = namesgenerator.get_sane_name(process_id, **self.sane_name_config)
        if self.collection.count({'identifier': sane_name}) > 0:
            if overwrite:
                self.collection.delete_one({'identifier': sane_name})
            else:
                raise ProcessRegistrationError("Process `{}` already registered.".format(sane_name))
        process.identifier = sane_name  # must use property getter/setter to match both 'Process' types
        self._add_process(process)
        return self.fetch_by_id(sane_name)

    def delete_process(self, process_id, visibility=None, request=None):
        """
        Removes process from database, optionally filtered by visibility.
        """
        sane_name = namesgenerator.get_sane_name(process_id, **self.sane_name_config)
        process = self.fetch_by_id(sane_name, visibility=visibility, request=request)
        if not process:
            raise ProcessNotFound("Process `{}` could not be found.".format(sane_name))
        return bool(self.collection.delete_one({'identifier': sane_name}).deleted_count)

    def list_processes(self, visibility=None, request=None):
        """
        Lists all processes in database, optionally filtered by visibility.

        :param visibility: One value amongst `twitcher.visibility`.
        :param request:
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
        search_filters['visibility'] = {'$in': list(visibility)}
        for process in self.collection.find(search_filters).sort('identifier', pymongo.ASCENDING):
            db_processes.append(ProcessDB(process))
        return db_processes

    def fetch_by_id(self, process_id, visibility=None, request=None):
        """
        Get process for given ``name`` from storage, optionally filtered by visibility.

        :return: An instance of :class:`twitcher.datatype.Process`.
        """
        sane_name = namesgenerator.get_sane_name(process_id, **self.sane_name_config)
        process = self.collection.find_one({'identifier': sane_name})
        if not process:
            raise ProcessNotFound("Process `{}` could not be found.".format(sane_name))
        process = ProcessDB(process)
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
        self.save_process(process, overwrite=True)

    def clear_processes(self, request=None):
        """
        Clears all processes from the store.
        """
        self.collection.drop()
        return True


class MongodbJobStore(JobStore, MongodbStore):
    """
    Registry for OWS service process jobs tracking. Uses mongodb to store job attributes.
    """

    def __init__(self, *args, **kwargs):
        JobStore.__init__(self)
        MongodbStore.__init__(self, *args, **kwargs)

    def save_job(self, task_id, process, service=None, inputs=None, is_workflow=False,
                 user_id=None, execute_async=True, custom_tags=None):
        """
        Stores a job in mongodb.
        """
        try:
            tags = ['dev']
            tags.extend(custom_tags or list())
            if is_workflow:
                tags.append('workflow')
            else:
                tags.append('single')
            if execute_async:
                tags.append('async')
            else:
                tags.append('sync')
            new_job = Job({
                'task_id': task_id,
                'user_id': user_id,
                'service': service,     # provider identifier (WPS service)
                'process': process,     # process identifier (WPS request)
                'inputs': inputs,
                'status': map_status(STATUS_ACCEPTED),
                'execute_async': execute_async,
                'is_workflow': is_workflow,
                'created': now(),
                'tags': tags,
            })
            self.collection.insert_one(new_job)
            job = self.fetch_by_id(job_id=new_job.id)
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
            result = self.collection.update_one({'id': job.id}, {'$set': job.params})
            if result.acknowledged and result.modified_count == 1:
                return self.fetch_by_id(job.id)
        except Exception as ex:
            raise JobUpdateError("Error occurred during job update: [{}]".format(repr(ex)))
        raise JobUpdateError("Failed to update specified job: `{}`".format(str(job)))

    def delete_job(self, job_id, request=None):
        """
        Removes job from mongodb storage.
        """
        self.collection.delete_one({'id': job_id})
        return True

    def fetch_by_id(self, job_id, request=None):
        """
        Gets job for given ``job_id`` from mongodb storage.
        """
        job = self.collection.find_one({'id': job_id})
        if not job:
            raise JobNotFound("Could not find job matching: `{}`".format(job_id))
        return Job(job)

    def list_jobs(self, request=None):
        """
        Lists all jobs in mongodb storage.
        """
        jobs = []
        for job in self.collection.find().sort('id', ASCENDING):
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


class MongodbQuoteStore(QuoteStore, MongodbStore):
    """
    Registry for quotes. Uses mongodb to store quote attributes.
    """

    def __init__(self, *args, **kwargs):
        QuoteStore.__init__(self)
        MongodbStore.__init__(self, *args, **kwargs)

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
            raise QuoteNotFound("Invalid sorting method: `{!s}`".format(sort))

        sort_order = ASCENDING
        sort_criteria = [(sort, sort_order)]
        found = self.collection.find(search_filters)
        count = found.count()
        items = [Quote(item) for item in list(found.skip(page * limit).limit(limit).sort(sort_criteria))]
        return items, count


class MongodbBillStore(BillStore, MongodbStore):
    """
    Registry for bills. Uses mongodb to store bill attributes.
    """

    def __init__(self, *args, **kwargs):
        BillStore.__init__(self)
        MongodbStore.__init__(self, *args, **kwargs)

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
