"""
Definitions of types used by tokens.
"""

import six
import time
import uuid
from datetime import datetime
from logging import _levelNames, ERROR, INFO
from twitcher.utils import now_secs
from twitcher.exceptions import ProcessInstanceError
from twitcher.processes import process_mapping
from twitcher.processes.types import PACKAGE_PROCESSES, PROCESS_WPS
from twitcher.wps_restapi.status import job_status_values
from pywps import Process as ProcessWPS


class Service(dict):
    """
    Dictionary that contains OWS services. It always has ``'url'`` key.
    """
    def __init__(self, *args, **kwargs):
        super(Service, self).__init__(*args, **kwargs)
        if 'url' not in self:
            raise TypeError("'url' is required")

    @property
    def url(self):
        """Service URL."""
        return self['url']

    @property
    def name(self):
        """Service name."""
        return self.get('name', 'unknown')

    @property
    def type(self):
        """Service type."""
        return self.get('type', 'WPS')

    @property
    def public(self):
        """Flag if service has public access."""
        # TODO: public access can be set via auth parameter.
        return self.get('public', False)

    @property
    def auth(self):
        """Authentication method: public, token, cert."""
        return self.get('auth', 'token')

    @property
    def params(self):
        return {
            'url': self.url,
            'name': self.name,
            'type': self.type,
            'public': self.public,
            'auth': self.auth}

    def __str__(self):
        return self.name

    def __repr__(self):
        cls = type(self)
        repr_ = dict.__repr__(self)
        return '{0}.{1}({2})'.format(cls.__module__, cls.__name__, repr_)


class Job(dict):
    """
    Dictionary that contains OWS service jobs. It always has ``'task_id'`` and ``identifier`` keys.
    """
    def __init__(self, *args, **kwargs):
        super(Job, self).__init__(*args, **kwargs)
        if 'task_id' not in self:
            raise TypeError("Parameter `task_id` is required for `{}` creation.".format(type(self)))
        if not isinstance(self['task_id'], six.string_types):
            raise TypeError("Type `str` is required for `{}.task_id`".format(type(self)))

    def _get_log_msg(self, msg=None):
        if not msg:
            msg = self.status_message
        return '{dur} {lvl:3d}% {stat:10} {msg}'.format(dur=self.duration, lvl=self.progress, stat=self.status, msg=msg)

    def save_log(self, errors=None, logger=None):
        if isinstance(errors, six.string_types):
            log_msg = [(ERROR, self._get_log_msg())]
            self.exceptions.append(errors)
        elif isinstance(errors, list):
            log_msg = [(ERROR, self._get_log_msg('{0.text} - code={0.code} - locator={0.locator}'.format(error)))
                       for error in errors]
            self.exceptions.extend([{
                    'Code': error.code,
                    'Locator': error.locator,
                    'Text': error.text
                } for error in errors])
        else:
            log_msg = [(INFO, self._get_log_msg())]
        for level, msg in log_msg:
            fmt_msg = '{0} {1:6} {2}'.format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), _levelNames[level], msg)
            if len(self.logs) == 0 or self.logs[-1] != fmt_msg:
                self.logs.append(fmt_msg)
                if logger:
                    logger.log(level, msg)

    @property
    def task_id(self):
        return self['task_id']

    @property
    def service(self):
        return self.get('service', None)

    @service.setter
    def service(self, service):
        if not isinstance(service, six.string_types):
            raise TypeError("Type `str` is required for `{}.service`".format(type(self)))
        self['service'] = service

    @property
    def process(self):
        return self.get('process', None)

    @process.setter
    def process(self, process):
        if not isinstance(process, six.string_types):
            raise TypeError("Type `str` is required for `{}.process`".format(type(self)))
        self['process'] = process

    @property
    def user_id(self):
        return self.get('user_id', None)

    @user_id.setter
    def user_id(self, user_id):
        if not isinstance(user_id, int):
            raise TypeError("Type `int` is required for `{}.user_id`".format(type(self)))
        self['user_id'] = user_id

    @property
    def status(self):
        return self.get('status', 'unknown')

    @status.setter
    def status(self, status):
        if not isinstance(status, six.string_types):
            raise TypeError("Type `str` is required for `{}.status`".format(type(self)))
        if status not in job_status_values:
            raise ValueError("Status `{0}` is not valid for `{1}.status`".format(status, type(self)))
        self['status'] = status

    @property
    def status_message(self):
        return self.get('status_message', 'no message')

    @status_message.setter
    def status_message(self, message):
        if message is None:
            return
        if not isinstance(message, six.string_types):
            raise TypeError("Type `str` is required for `{}.status_message`".format(type(self)))
        self['status_message'] = message

    @property
    def status_location(self):
        return self.get('status_location', None)

    @status_location.setter
    def status_location(self, location_url):
        if not isinstance(location_url, six.string_types):
            raise TypeError("Type `str` is required for `{}.status_location`".format(type(self)))
        self['status_location'] = location_url

    @property
    def is_workflow(self):
        return self.get('is_workflow', False)

    @is_workflow.setter
    def is_workflow(self, is_workflow):
        if not isinstance(is_workflow, bool):
            raise TypeError("Type `bool` is required for `{}.is_workflow`".format(type(self)))
        self['is_workflow'] = is_workflow

    @property
    def created(self):
        created = self.get('created', None)
        if not created:
            self['created'] = datetime.now()
        return self.get('created')

    @property
    def finished(self):
        return self.get('finished', None)

    def is_finished(self):
        self['finished'] = datetime.now()

    @property
    def duration(self):
        final_time = self.finished or datetime.now()
        duration = final_time - self.created
        self['duration'] = str(duration).split('.')[0]
        return self['duration']

    @property
    def progress(self):
        return self.get('progress', 0)

    @progress.setter
    def progress(self, progress):
        if not isinstance(progress, (int, float)):
            raise TypeError("Number is required for `{}.progress`".format(type(self)))
        if progress < 0 or progress > 100:
            raise ValueError("Value must be in range [0,100] for `{}.progress`".format(type(self)))
        self['progress'] = progress

    def _get_results(self):
        if self.get('results') is None:
            self['results'] = list()
        return self['results']

    def _set_results(self, results):
        if not isinstance(results, list):
            raise TypeError("Type `list` is required for `{}.results`".format(type(self)))
        self['results'] = results

    # allows to correctly update list by ref using `job.results.extend()`
    results = property(_get_results, _set_results)

    def _get_exceptions(self):
        if self.get('exceptions') is None:
            self['exceptions'] = list()
        return self['exceptions']

    def _set_exceptions(self, exceptions):
        if not isinstance(exceptions, list):
            raise TypeError("Type `list` is required for `{}.exceptions`".format(type(self)))
        self['exceptions'] = exceptions

    # allows to correctly update list by ref using `job.exceptions.extend()`
    exceptions = property(_get_exceptions, _set_exceptions)

    def _get_logs(self):
        if self.get('logs') is None:
            self['logs'] = list()
        return self['logs']

    def _set_logs(self, logs):
        if not isinstance(logs, list):
            raise TypeError("Type `list` is required for `{}.logs`".format(type(self)))
        self['logs'] = logs

    # allows to correctly update list by ref using `job.logs.extend()`
    logs = property(_get_logs, _set_logs)

    def _get_tags(self):
        if self.get('tags') is None:
            self['tags'] = list()
        return self['tags']

    def _set_tags(self, tags):
        if not isinstance(tags, list):
            raise TypeError("Type `list` is required for `{}.tags`".format(type(self)))
        self['tags'] = tags

    # allows to correctly update list by ref using `job.tags.extend()`
    tags = property(_get_tags, _set_tags)

    @property
    def request(self):
        return self.get('request', None)

    @request.setter
    def request(self, request):
        self['request'] = request

    @property
    def response(self):
        return self.get('response', None)

    @response.setter
    def response(self, response):
        self['response'] = response

    @property
    def params(self):
        return {
            'task_id': self.task_id,
            'service': self.service,
            'process': self.process,
            'user_id': self.user_id,
            'status': self.status,
            'status_message': self.status_message,
            'status_location': self.status_location,
            'is_workflow': self.is_workflow,
            'created': self.created,
            'finished': self.finished,
            'duration': self.duration,
            'progress': self.progress,
            'results': self.results,
            'exceptions': self.exceptions,
            'logs': self.logs,
            'tags': self.tags,
            'request': self.request,
            'response': self.response,
        }

    def __str__(self):
        return 'Job <{}>'.format(self.task_id)

    def __repr__(self):
        cls = type(self)
        repr_ = dict.__repr__(self)
        return '{0}.{1}({2})'.format(cls.__module__, cls.__name__, repr_)


class AccessToken(dict):
    """
    Dictionary that contains access token. It always has ``'token'`` key.
    """

    def __init__(self, *args, **kwargs):
        super(AccessToken, self).__init__(*args, **kwargs)
        if 'token' not in self:
            raise TypeError("'token' is required")

    @property
    def token(self):
        """Access token string."""
        return self['token']

    @property
    def expires_at(self):
        return int(self.get("expires_at", 0))

    @property
    def expires_in(self):
        """
        Returns the time until the token expires.
        :return: The remaining time until expiration in seconds or 0 if the
                 token has expired.
        """
        time_left = self.expires_at - now_secs()

        if time_left > 0:
            return time_left
        return 0

    def is_expired(self):
        """
        Determines if the token has expired.
        :return: `True` if the token has expired. Otherwise `False`.
        """
        if self.expires_at is None:
            return True

        if self.expires_in > 0:
            return False

        return True

    @property
    def data(self):
        return self.get('data') or {}

    @property
    def params(self):
        return {'access_token': self.token, 'expires_at': self.expires_at}

    def __str__(self):
        return self.token

    def __repr__(self):
        cls = type(self)
        repr_ = dict.__repr__(self)
        return '{0}.{1}({2})'.format(cls.__module__, cls.__name__, repr_)


class Process(dict):
    """
    Dictionary that contains a process description for db storage.
    It always has ``'identifier'`` and ``executeEndpoint`` keys.
    """

    def __init__(self, *args, **kwargs):
        super(Process, self).__init__(*args, **kwargs)
        # use both 'id' and 'identifier' to support any call (WPS and recurrent 'id')
        if 'id' not in self and 'identifier' not in self:
            raise TypeError("'id' OR 'identifier' is required")
        if not self.get('identifier'):
            self['identifier'] = self.pop('id')
        if 'executeEndpoint' not in self:
            raise TypeError("'executeEndpoint' is required")
        if 'package' not in self:
            raise TypeError("'package' is required")

    @property
    def id(self):
        return self.identifier

    @property
    def identifier(self):
        return self['identifier']

    @property
    def title(self):
        return self.get('title', self.id)

    @property
    def abstract(self):
        return self.get('abstract', '')

    @property
    def keywords(self):
        return self.get('keywords', [])

    @property
    def metadata(self):
        return self.get('metadata', [])

    @property
    def version(self):
        return self.get('version')

    @property
    def inputs(self):
        return self.get('inputs')

    @property
    def outputs(self):
        return self.get('outputs')

    @property
    def jobControlOptions(self):
        return self.get('jobControlOptions')

    @property
    def outputTransmission(self):
        return self.get('outputTransmission')

    @property
    def executeEndpoint(self):
        return self.get('executeEndpoint')

    # wps, workflow, etc.
    @property
    def type(self):
        return self.get('type')

    @property
    def package(self):
        return self.get('package')

    def __str__(self):
        return "Process <{0}> ({1})".format(self.identifier, self.title)

    def __repr__(self):
        cls = type(self)
        repr_ = dict.__repr__(self)
        return '{0}.{1}({2})'.format(cls.__module__, cls.__name__, repr_)

    @property
    def params(self):
        return {
            'identifier': self.identifier,
            'title': self.title,
            'abstract': self.abstract,
            'keywords': self.keywords,
            'metadata': self.metadata,
            'version': self.version,
            'inputs': self.inputs,
            'outputs': self.outputs,
            'jobControlOptions': self.jobControlOptions,
            'outputTransmission': self.outputTransmission,
            'executeEndpoint': self.executeEndpoint,
            'type': self.type,
            'package': self.package,      # deployment specification (json body)
        }

    @property
    def params_wps(self):
        """Values applicable to WPS Process __init__
        """
        return {
            'identifier': self.identifier,
            'title': self.title,
            'abstract': self.abstract,
            'keywords': self.keywords,
            'metadata': self.metadata,
            'version': self.version,
            'inputs': self.inputs,
            'outputs': self.outputs,
        }

    def json(self):
        return {
            'identifier': self.identifier,
            'title': self.title,
            'abstract': self.abstract,
            'keywords': self.keywords,
            'metadata': self.metadata,
            'version': self.version,
            'inputs': self.inputs,
            'outputs': self.outputs,
            'jobControlOptions': self.jobControlOptions,
            'outputTransmission': self.outputTransmission,
            'executeEndpoint': self.executeEndpoint,
        }

    def summary(self):
        return {
            'identifier': self.identifier,
            'title': self.title,
            'abstract': self.abstract,
            'keywords': self.keywords,
            'metadata': self.metadata,
            'version': self.version,
            'jobControlOptions': self.jobControlOptions,
            'executeEndpoint': self.executeEndpoint,
        }

    @staticmethod
    def from_wps(wps_process, **extra_params):
        assert isinstance(wps_process, ProcessWPS)
        process = wps_process.json
        process.update({'type': wps_process.identifier, 'package': None, 'reference': None})
        process.update(**extra_params)
        return Process(process)

    def wps(self):
        process_key = self.type
        if self.type == PROCESS_WPS:
            process_key = self.identifier
        if process_key not in process_mapping:
            ProcessInstanceError("Unknown process `{}` in mapping".format(process_key))
        if process_key in PACKAGE_PROCESSES:
            kwargs = self.params_wps
            kwargs.update({'package': self.package})
            return process_mapping[process_key](**kwargs)
        return process_mapping[process_key]()


class Quote(dict):
    """
    Dictionary that contains quote information.
    It always has ``'id'`` and ``process`` key.
    """
    def __init__(self, *args, **kwargs):
        super(Quote, self).__init__(*args, **kwargs)
        if 'process' not in self:
            raise TypeError("'process' is required")
        self['id'] = str(uuid.uuid4())

    @property
    def id(self):
        """Quote ID."""
        return self['id']

    @property
    def process(self):
        """WPS Process ID."""
        return self['process']

    @property
    def cost(self):
        return self.get('cost', 0.0)

    @property
    def params(self):
        return {
            'id': self.id,
            'cost': self.cost,
            'process': self.process,
        }

    def json(self):
        return self.params

    def __str__(self):
        return "Quote <{0}>".format(self.id)

    def __repr__(self):
        cls = type(self)
        repr_ = dict.__repr__(self)
        return '{0}.{1}({2})'.format(cls.__module__, cls.__name__, repr_)


class Bill(dict):
    """
    Dictionary that contains bill information.
    It always has ``'id'`` and ``quote`` key.
    """
    def __init__(self, *args, **kwargs):
        super(Bill, self).__init__(*args, **kwargs)
        if 'quote' not in self:
            raise TypeError("'quote' is required")
        self['id'] = str(uuid.uuid4())

    @property
    def id(self):
        """Bill ID."""
        return self['id']

    @property
    def quote(self):
        """Quote ID."""
        return self['quote']

    @property
    def params(self):
        return {
            'id': self.id,
            'quote': self.quote,
        }

    def json(self):
        return self.params

    def __str__(self):
        return "Bill <{0}>".format(self.id)

    def __repr__(self):
        cls = type(self)
        repr_ = dict.__repr__(self)
        return '{0}.{1}({2})'.format(cls.__module__, cls.__name__, repr_)
