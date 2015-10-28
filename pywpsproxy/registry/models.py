import pymongo
from urlparse import urlparse
import uuid

from pywpsproxy.exceptions import OWSServiceNotFound, OWSServiceException
from pywpsproxy.utils import namesgenerator

import logging
logger = logging.getLogger(__name__)

def add_service(request, url, identifier=None):
    # TODO: check url ... reduce it to base url
    # check for full url
    parsed_url = urlparse(url)
    if not parsed_url.netloc or parsed_url.scheme not in ("http", "https"):
        raise OWSServiceException("bad url.")
    service_url = "%s://%s%s" % (parsed_url.scheme, parsed_url.netloc, parsed_url.path.strip())
    # check if service is already registered
    service = request.db.services.find_one({'url': service_url})
    if service is None:
        if identifier is None:
            identifier = namesgenerator.get_random_name()
            if not request.db.services.find_one({'identifier': identifier}) is None:
                identifier = namesgenerator.get_random_name(retry=True)
        service = dict(identifier = identifier, url = service_url)
        if request.db.services.find_one({'identifier': identifier}):
            raise OWSServiceException("identifier %s already registered." % (identifier))
        request.db.services.insert_one(service)
        service = request.db.services.find_one({'identifier': service['identifier']})
    return service

def service_url(request, identifier):
    service = request.db.services.find_one({'identifier': identifier})
    if service is None:
        raise OWSServiceNotFound('service not found')
    if not 'url' in service:
        raise OWSServiceNotFound('service has no url')
    return service.get('url')


def clear(request):
    """
    removes all services.
    """
    request.db.services.drop()
    





