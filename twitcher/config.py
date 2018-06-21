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


def parse_extra_options(option_str):
    """
    Parses the extra options parameter.

    The option_str is a string with ``opt=value`` pairs.

    Example::

        tempdir=/path/to/tempdir
        archive_root=/path/to/archive

    :param option_str: A string parameter with the extra options.
    :return: A dict with the parsed extra options.
    """
    if option_str:
        try:
            extra_options = option_str.split(',')
            extra_options = dict([('=' in opt) and opt.split('=', 1) for opt in extra_options])
        except Exception:
            msg = "Can not parse extra-options: {}".format(option_str)
            logging.exception(msg)
            raise zc.buildout.UserError(msg)
    else:
        extra_options = {}
    return extra_options


def includeme(config):
    # settings = config.registry.settings

    LOGGER.debug("Loading twitcher configuration.")

    config.add_request_method(_workdir, 'workdir', reify=True)
    config.add_request_method(_prefix, 'prefix', reify=True)

    settings = config.registry.settings
    config.add_settings(parse_extra_options(settings.get('twitcher.extra_options', '')))
