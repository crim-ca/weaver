import pymongo
import uuid
from datetime import timedelta
from utils import now, localize_datetime

from pyramid.httpexceptions import (HTTPForbidden, HTTPBadRequest,
                                    HTTPBadGateway, HTTPNotAcceptable)

from exceptions import TokenNotValid, OWSServiceNotFound

import logging
logger = logging.getLogger(__name__)

def mongodb(registry):
    settings = registry.settings
    client = pymongo.MongoClient(settings['mongodb.host'], int(settings['mongodb.port']))
    return client[settings['mongodb.db_name']]


# ows registry

def register_service(request, url):
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

# tokens

def create_token(request):
    token = dict(
        identifier = str(uuid.uuid1()),
        creation_time = now(),
        valid_in_hours = 1)
    request.db.tokens.insert_one(token)
    return request.db.tokens.find_one({'identifier':token['identifier']})

def get_token(request, identifier):
    return request.db.tokens.find_one({'identifier': identifier})

def validate_token(request, identifier):
    try:
        token = request.db.tokens.find_one({'identifier': identifier})
        if token is None: # invalid token
            raise TokenNotValid("no token found")
        not_before = localize_datetime(token['creation_time'])
        if not_before > now(): # not before
            return TokenNotValid("token not valid")
        not_after = not_before + timedelta(hours=token['valid_in_hours'])
        if not_after < now(): # not after
            return TokenNotValid("token not valid")
    except TokenNotValid:
        logger.warn('accessed with invalid token')
        raise

def remove_token(request, identifier):
    request.db.tokens.delete_one({'identifier': identifier})
    





