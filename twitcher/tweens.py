import tempfile

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
        config.add_request_method(_workdir, 'workdir', reify=True)
        config.add_request_method(_prefix, 'prefix', reify=True)
        config.add_request_method(_esgf_test_credentials, 'esgf_test_credentials', reify=True)


def _workdir(request):
    settings = request.registry.settings
    workdir = settings.get('twitcher.workdir')
    workdir = workdir or tempfile.gettempdir()
    logger.debug('using workdir %s', workdir)
    return workdir


def _prefix(request):
    settings = request.registry.settings
    prefix = settings.get('twitcher.prefix')
    prefix = prefix or 'pywps_process_'
    return prefix


def _esgf_test_credentials(request):
    settings = request.registry.settings
    credentials = settings.get('twitcher.esgf_test_credentials')
    if credentials:
        logger.warn('using esgf test credentials %s', credentials)
    else:
        credentials = None
    return credentials


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
