from pyramid.settings import asbool
from pyramid.tweens import EXCVIEW

from twitcher.owsexceptions import (OWSException,
                                    OWSAccessForbidden,
                                    OWSNoApplicableCode,
                                    OWSMissingParameterValue,
                                    OWSInvalidParameterValue)
from twitcher.owsrequest import OWSRequest
from twitcher.owssecurity import owssecurity_factory
from twitcher.utils import path_elements

import logging
logger = logging.getLogger(__name__)

def includeme(config):
    settings = config.registry.settings

    if asbool(settings.get('twitcher.ows_security', True)):
        logger.info('Add OWS security tween')
        config.add_tween(OWS_SECURITY, under=EXCVIEW)


def ows_security_tween_factory(handler, registry):
    """A tween factory which produces a tween which raises an exception
    if access to OWS service is not allowed."""

    allowed_service_types = ('wps',)
    allowed_requests = ('getcapabilities', 'describeprocess')
    protected_path = '/ows/'

    security = owssecurity_factory(registry)
 
    def ows_security_tween(request):
        try:
            if request.path.startswith(protected_path):
                ows_request = OWSRequest(request)
                if not ows_request.service in allowed_service_types:
                    raise OWSInvalidParameterValue(
                        "service %s not supported" % ows_request.service, value="service")
                if not ows_request.request in allowed_requests:
                    token = security.get_token(request)
                    access_token = security.validate_token(token)
                    # update request with user environ from access token
                    request.environ.update( access_token.user_environ )
            return handler(request)
        except OWSException as err:
            logger.exception("security check failed.")
            return err
        except Exception as err:
            logger.exception("unknown error")
            return OWSNoApplicableCode(err.message)
        
    return ows_security_tween

OWS_SECURITY = 'twitcher.tweens.ows_security_tween_factory'
