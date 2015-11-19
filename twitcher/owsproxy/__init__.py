"""
The owsproxy is based on `papyrus_ogcproxy <https://github.com/elemoine/papyrus_ogcproxy>`_
"""

from pyramid.config import Configurator
import pyramid.tweens
from twitcher.tweens import OWS_SECURITY

def includeme(config):
    """ The callable makes it possible to include owsproxy
    in a Pyramid application.

    Calling ``config.include(twitcher.owsproxy)`` will result in this
    callable being called.

    Arguments:

    * ``config``: the ``pyramid.config.Configurator`` object.
    """
    config.add_route('owsproxy', '/ows/proxy/{service_name}')
    config.add_route('owsproxy_secured', '/ows/proxy/{service_name}/{access_token}')

    # add tweens
    config.add_tween(OWS_SECURITY, under=pyramid.tweens.EXCVIEW)

