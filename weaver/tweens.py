from pyramid.tweens import EXCVIEW
from weaver.owsexceptions import OWSException, OWSNoApplicableCode, OWSNotImplemented, OWSNotAcceptable  # noqa: F401

import logging
logger = logging.getLogger(__name__)


def includeme(config):
    config.add_tween(OWS_RESPONSE, under=EXCVIEW)


# noinspection PyUnusedLocal
def ows_response_tween_factory(handler, registry):
    """A tween factory which produces a tween which transforms common
    exceptions into OWS specific exceptions."""

    def ows_response_tween(request):
        try:
            return handler(request)
        except NotImplementedError as err:
            return OWSNotImplemented(str(err))
        except OWSException as err:
            return err

    return ows_response_tween


OWS_RESPONSE = 'weaver.tweens.ows_response_tween_factory'
