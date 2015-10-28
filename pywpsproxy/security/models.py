import pymongo
import uuid
from datetime import timedelta
from pywpsproxy.utils import now, localize_datetime

from pywpsproxy.exceptions import TokenNotValid

import logging
logger = logging.getLogger(__name__)

def create_token(request):
    token = dict(
        identifier = str(uuid.uuid1().get_hex()),
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
    





