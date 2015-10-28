import pymongo
import uuid

from pywpsproxy.exceptions import OWSServiceNotFound

import logging
logger = logging.getLogger(__name__)

def add_service(request, url):
    service = dict(
        identifier = str(uuid.uuid1()),
        url = url)
    request.db.services.insert_one(service)
    return request.db.services.find_one({'identifier': service['identifier']})

def service_url(request, service_id):
    service = request.db.services.find_one({'identifier': service_id})
    if service is None:
        raise OWSServiceNotFound('service not found')
    if not 'url' in service:
        logger.error('service has no url')
        raise OWSServiceNotFound('service has no url')
    return service.get('url')






