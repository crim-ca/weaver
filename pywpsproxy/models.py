import pymongo
import uuid
from datetime import timedelta
from utils import now, localize_datetime

import logging
logger = logging.getLogger(__name__)

def mongodb(registry):
    settings = registry.settings
    client = pymongo.MongoClient(settings['mongodb.host'], int(settings['mongodb.port']))
    return client[settings['mongodb.db_name']]

def create_token(request):
    token = dict(
        identifier = str(uuid.uuid1()),
        creation_time = now(),
        valid_in_hours = 1)
    request.db.tokens.insert_one(token)
    return request.db.tokens.find_one({'identifier':token['identifier']})

def get_token(request, identifier):
    return request.db.tokens.find_one({'identifier': identifier})

def is_token_valid(request, identifier):
    try:
        token = request.db.tokens.find_one({'identifier': identifier})
        if token is None: # invalid token
            return False
        not_before = localize_datetime(token['creation_time'])
        if not_before > now(): # not before
            logger.debug('check not before failed')
            return False
        not_after = not_before + timedelta(hours=token['valid_in_hours'])
        if not_after < now(): # not after
            logger.debug('check not after failed')
            return False
    except:
        logger.exception('failed')
        return False
    return True

def remove_token(request, identifier):
    request.db.tokens.delete_one({'identifier': identifier})
    





