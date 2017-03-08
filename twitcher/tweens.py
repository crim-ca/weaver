from pyramid.settings import asbool
from pyramid.tweens import EXCVIEW

from twitcher.owsexceptions import OWSException, OWSNoApplicableCode
from twitcher.owssecurity import owssecurity_factory

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

    security = owssecurity_factory(registry)

    def ows_security_tween(request):
        try:
            security.check_request(request)
            return handler(request)
        except OWSException as err:
            logger.exception("security check failed.")
            return err
        except Exception as err:
            logger.exception("unknown error")
            return OWSNoApplicableCode(err.message)

    return ows_security_tween


OWS_SECURITY = 'twitcher.tweens.ows_security_tween_factory'
