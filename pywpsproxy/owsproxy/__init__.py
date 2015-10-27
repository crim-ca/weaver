"""
The owsproxy is based on `papyrus_ogcproxy <https://github.com/elemoine/papyrus_ogcproxy>`_
"""

from pyramid.config import Configurator

def includeme(config):
    """ The callable makes it possible to include owsproxy
    in a Pyramid application.

    Calling ``config.include(pywpsproxy.owsproxy)`` will result in this
    callable being called.

    Arguments:

    * ``config``: the ``pyramid.config.Configurator`` object.
    """
    config.add_route('owsproxy', '/owsproxy/{ows_service}/{token}')

