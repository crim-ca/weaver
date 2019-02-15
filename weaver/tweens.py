from pyramid.settings import asbool
from pyramid.tweens import EXCVIEW
from pyramid.httpexceptions import HTTPException, HTTPBadRequest
from weaver.owsexceptions import OWSException, OWSNoApplicableCode, OWSNotImplemented, OWSNotAcceptable
from weaver.adapter import owssecurity_factory

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
