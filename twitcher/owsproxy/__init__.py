"""
The owsproxy is based on `papyrus_ogcproxy <https://github.com/elemoine/papyrus_ogcproxy>`_
"""

from pyramid.config import Configurator
from twitcher.tween import OWS_SECURITY

def includeme(config):
    """ The callable makes it possible to include owsproxy
    in a Pyramid application.

    Calling ``config.include(twitcher.owsproxy)`` will result in this
    callable being called.

    Arguments:

    * ``config``: the ``pyramid.config.Configurator`` object.
    """
    config.add_route('owsproxy', '/owsproxy/{service_id}')
    config.add_route('owsproxy_secured', '/owsproxy/{service_id}/{tokenid}')

    # add tweens
    config.add_tween(OWS_SECURITY)

