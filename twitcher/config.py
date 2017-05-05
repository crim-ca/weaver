import os
import tempfile

from pyramid.settings import asbool


import logging
LOGGER = logging.getLogger("TWITCHER")


def _workdir(request):
    settings = request.registry.settings
    workdir = settings.get('twitcher.workdir')
    workdir = workdir or tempfile.gettempdir()
    if not os.path.exists(workdir):
        os.makedirs(workdir)
    LOGGER.debug('using workdir %s', workdir)
    return workdir


def _prefix(request):
    settings = request.registry.settings
    prefix = settings.get('twitcher.prefix')
    prefix = prefix or 'twitcher_'
    return prefix


def includeme(config):
    # settings = config.registry.settings

    LOGGER.debug("Loading twitcher configuration.")

    config.add_request_method(_workdir, 'workdir', reify=True)
    config.add_request_method(_prefix, 'prefix', reify=True)
