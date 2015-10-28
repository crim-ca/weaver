import pymongo
import uuid

from pywpsproxy.exceptions import OWSServiceNotFound

import logging
logger = logging.getLogger(__name__)

def add_service(request, url):
    # TODO: check url ... reduce it to base url
    # check if service is already registered
    service = request.db.services.find_one({'url': url})
    if service is None:
        service = dict(
            identifier = str(uuid.uuid1().get_hex()),
            url = url)
        request.db.services.insert_one(service)
        service = request.db.services.find_one({'identifier': service['identifier']})
    return service

def service_url(request, service_id):
    service = request.db.services.find_one({'identifier': service_id})
    if service is None:
        raise OWSServiceNotFound('service not found')
    if not 'url' in service:
        logger.error('service has no url')
        raise OWSServiceNotFound('service has no url')
    return service.get('url')


def clear(request):
    """
    removes all services.
    """
    request.db.services.drop()
    





