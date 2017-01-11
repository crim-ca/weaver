import tempfile

from pyramid.settings import asbool


import logging
logger = logging.getLogger(__name__)


def _workdir(request):
    settings = request.registry.settings
    workdir = settings.get('twitcher.workdir')
    workdir = workdir or tempfile.gettempdir()
    logger.debug('using workdir %s', workdir)
    return workdir


def _prefix(request):
    settings = request.registry.settings
    prefix = settings.get('twitcher.prefix')
    prefix = prefix or 'twitcher_'
    return prefix


def includeme(config):
    # settings = config.registry.settings

    logger.debug("Loading twitcher configuration.")

    config.add_request_method(_workdir, 'workdir', reify=True)
    config.add_request_method(_prefix, 'prefix', reify=True)
