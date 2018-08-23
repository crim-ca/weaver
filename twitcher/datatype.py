"""
Definitions of types used by tokens.
"""

import six
import time
import uuid
from datetime import datetime
from twitcher.utils import now_secs
from twitcher.exceptions import AccessTokenNotFound
from twitcher.wps_restapi.status import status_values


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

    def save_log(self, errors=None, logger=None):
        if isinstance(errors, six.string_types):
            errors = list(errors)
        if isinstance(errors, list):
            log_msg = ['ERROR: {0.text} - code={0.code} - locator={0.locator}'.format(error) for error in errors]
            self.exceptions.extend([{
                    'Code': error.code,
                    'Locator': error.locator,
                    'Text': error.text
                } for error in errors])
        else:
            log_msg = ['{0} {1:3d}%: {2}'.format(self.duration, self.progress, self.status_message)]
        # skip same log messages
        if len(self.logs) == 0 or self.logs[-1] != log_msg[0]:
            self.logs.extend(log_msg)
            if logger:
                for msg in log_msg:
                    if errors:
                        logger.error(msg)
                    else:
                        logger.info(msg)

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
        if status not in status_values:
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
        return self.get('status_message', None)

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

    @property
    def results(self):
        return self.get('results', list())

    @results.setter
    def results(self, results):
        if not isinstance(results, list):
            raise TypeError("Type `list` is required for `{}.results`".format(type(self)))
        self['results'] = results

    @property
    def exceptions(self):
        return self.get('exceptions', list())

    @exceptions.setter
    def exceptions(self, exceptions):
        if not isinstance(exceptions, list):
            raise TypeError("Type `list` is required for `{}.exceptions`".format(type(self)))
        self['exceptions'] = exceptions

    @property
    def logs(self):
        return self.get('logs', list())

    @logs.setter
    def logs(self, logs):
        if not isinstance(logs, list):
            raise TypeError("Type `list` is required for `{}.logs`".format(type(self)))
        self['logs'] = logs

    @property
    def tags(self):
        return self.get('tags', list())

    @tags.setter
    def tags(self, tags):
        if not isinstance(tags, list):
            raise TypeError("Type `list` is required for `{}.tags`".format(type(self)))
        self['tags'] = tags

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
