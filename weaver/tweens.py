from pyramid.tweens import INGRESS
from pyramid.httpexceptions import HTTPException, HTTPInternalServerError
from weaver.owsexceptions import OWSException, OWSNotImplemented  # noqa: F401

import logging
LOGGER = logging.getLogger(__name__)


def includeme(config):
    # using 'INGRESS' to run `weaver.wps_restapi.api` views that fix HTTP code before OWS response,
    # using 'EXCVIEW' does the other way around
    config.add_tween(OWS_RESPONSE, under=INGRESS)


# noinspection PyUnusedLocal
def ows_response_tween_factory(handler, registry):
    """A tween factory which produces a tween which transforms common
    exceptions into OWS specific exceptions."""

    def ows_response_tween(request):
        try:
            return handler(request)
        except HTTPException as err:
            LOGGER.debug("http exception -> ows exception response.")
            # Use the same json formatter than OWSException
            err._json_formatter = OWSException.json_formatter
            return err
        except OWSException as err:
            LOGGER.debug('direct ows exception response')
            return err
        except NotImplementedError as err:
            LOGGER.debug('not implemented error -> ows exception response')
            return OWSNotImplemented(str(err))
        except Exception as err:
            LOGGER.debug("unhandled {!s} exception -> ows exception response".format(type(err).__name__))
            return OWSException(detail=str(err), status=HTTPInternalServerError)

    return ows_response_tween


OWS_RESPONSE = 'weaver.tweens.ows_response_tween_factory'
