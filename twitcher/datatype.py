"""
Definitions of types used by tokens.
"""

import time

from twitcher.utils import now_secs
from twitcher.exceptions import ProcessInstanceError
from twitcher.processes import process_mapping
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
    """

    def __init__(self, *args, **kwargs):
        super(Process, self).__init__(*args, **kwargs)
        if 'identifier' not in self:
            raise TypeError("'identifier' is required")
        if 'package' not in self:
            raise TypeError("'package' is required")

    @property
    def identifier(self):
        return self['identifier']

    @property
    def title(self):
        return self.get('title', self.identifier)

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
    def from_wps(wps_process):
        assert isinstance(wps_process, ProcessWPS)
        process = wps_process.json
        process.update({'type': wps_process.identifier, 'package': None, 'reference': None})
        return Process(process)

    def wps(self):
        process_key = self.type
        if self.type == 'wps':
            process_key = self.identifier
        if process_key not in process_mapping:
            ProcessInstanceError("Unknown process `{}` in mapping".format(process_key))
        if process_key == 'workflow':
            kwargs = self.params_wps
            kwargs.update({'package': self.package})
            return process_mapping[process_key](**kwargs)
        return process_mapping[process_key]()
