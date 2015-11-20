from twitcher.owssecurity import validate

import logging
logger = logging.getLogger(__name__)


def ows_security_tween_factory(handler, registry):
    """ A :term:`tween` factory which produces a tween which raises an exception
    if access to OWS service is not allowed."""

    def ows_security_tween(request):
        validate(request)
        return handler(request)
    return ows_security_tween

OWS_SECURITY = 'twitcher.tweens.ows_security_tween_factory'

