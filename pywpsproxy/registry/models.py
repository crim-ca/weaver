import pymongo
import uuid

from pywpsproxy.exceptions import OWSServiceNotFound
from pywpsproxy.utils import namesgenerator

import logging
logger = logging.getLogger(__name__)

def add_service(request, url, identifier=None):
    # TODO: check url ... reduce it to base url
    # check if service is already registered
    service = request.db.services.find_one({'url': url})
    if service is None:
        if identifier is None:
            identifier = namesgenerator.get_random_name()
        service = dict(identifier = identifier, url = url)
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
    





