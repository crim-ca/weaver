import pymongo
import uuid
from datetime import timedelta
from twitcher.utils import now, localize_datetime

from twitcher.exceptions import HTTPTokenNotValid

import logging
logger = logging.getLogger(__name__)


def create_token(request):
    """
    creates a token which is valid for 1 hour.

    TODO: specify valid in hours
    TODO: maybe specify how often a token can be used
    """
    token = dict(
        identifier = str(uuid.uuid1().get_hex()),
        creation_time = now(),
        valid_in_hours = 1)
    request.db.tokens.insert_one(token)
    return request.db.tokens.find_one({'identifier':token['identifier']})


def remove_token(request, tokenid):
    request.db.tokens.delete_one({'identifier': tokenid})

    
def get_token(request, identifier):
    return request.db.tokens.find_one({'identifier': identifier})


def validate_token(request):
    try:
        tokenid = None
        if not request.matchdict:
            # TODO: this is not the way to get the tokenid
            tokenid = request.path_info.split('/')[2]
        token = request.db.tokens.find_one({'identifier': tokenid})
        if token is None: # invalid token
            raise HTTPTokenNotValid("no token found")
        not_before = localize_datetime(token['creation_time'])
        if not_before > now(): # not before
            return HTTPTokenNotValid("token not valid")
        not_after = not_before + timedelta(hours=token['valid_in_hours'])
        if not_after < now(): # not after
            return HTTPTokenNotValid("token not valid")
    except:
        logger.exception('token validation failed. %s', request)
        raise


    





