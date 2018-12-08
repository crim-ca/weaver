from pyramid.settings import asbool
from pyramid.tweens import EXCVIEW
from pyramid.httpexceptions import HTTPException, HTTPBadRequest
from twitcher.owsexceptions import OWSException, OWSNoApplicableCode, OWSNotImplemented, OWSNotAcceptable
from twitcher.adapter import owssecurity_factory

import logging
logger = logging.getLogger(__name__)


def includeme(config):
    settings = config.registry.settings
    config.add_tween(OWS_RESPONSE, under=EXCVIEW)

    if asbool(settings.get('twitcher.ows_security', True)):
        logger.info('Add OWS security tween')
        config.add_tween(OWS_SECURITY, under=EXCVIEW)


def ows_response_tween_factory(handler, registry):
    """A tween factory which produces a tween which transforms common
    exceptions into OWS specific exceptions."""

    def ows_response_tween(request):
        try:
            return handler(request)
        except NotImplementedError as err:
            return OWSNotImplemented(err.message)
        except OWSException as err:
            return err

    return ows_response_tween


def ows_security_tween_factory(handler, registry):
    """A tween factory which produces a tween which raises an exception
    if access to OWS service is not allowed."""

    security = owssecurity_factory(registry)

    def ows_security_tween(request):
        try:
            security.check_request(request)
            return handler(request)
        except OWSException as err:
            logger.exception("security check failed.")
            return err
        except HTTPException as err:
            logger.exception("security check failed.")
            # Use the same json formatter than OWSException
            err._json_formatter = OWSException.json_formatter
            return err
        except Exception as err:
            logger.exception("unknown error")
            return OWSNoApplicableCode(err.message)

    return ows_security_tween


OWS_RESPONSE = 'twitcher.tweens.ows_response_tween_factory'
OWS_SECURITY = 'twitcher.tweens.ows_security_tween_factory'
