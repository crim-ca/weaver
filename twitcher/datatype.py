"""
Definitions of types used by tokens.
"""

import time
import uuid
from twitcher.utils import now_secs
from twitcher.exceptions import AccessTokenNotFound


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
            raise TypeError("'task_id' is required")
        self['identifier'] = uuid.uuid4().get_hex()

    @property
    def task_id(self):
        return self['task_id']

    @property
    def identifier(self):
        return self['identifier']

    @property
    def service(self):
        return self.get('service', None)

    @property
    def process(self):
        return self.get('process', None)

    @property
    def user_id(self):
        return self.get('user_id', None)

    @property
    def status(self):
        return self.get('status', 'unknown')

    @property
    def status_message(self):
        return self.get('status_message', '')

    @property
    def status_location(self):
        return self.get('status_message', None)

    @property
    def is_workflow(self):
        return self.get('is_workflow', False)

    @property
    def created(self):
        return self.get('created', None)

    @property
    def finished(self):
        return self.get('finished', None)

    @property
    def duration(self):
        return self.get('duration', None)

    @property
    def logs(self):
        return self.get('logs', list())

    @property
    def tags(self):
        return self.get('tags', list())

    @property
    def request(self):
        return self.get('request', list())

    @property
    def response(self):
        return self.get('response', list())

    @property
    def params(self):
        return {
            'task_id': self.task_id,
            'identifier': self.identifier,
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
