# code taken from https://github.com/elemoine/papyrus_ogcproxy

from pyramid.config import Configurator

def add_view(config):
    """ Add a view and a route to the ogcproxy view callable. The proxy
    service is made available at ``/ogcproxy``.

    Arguments:

    * ``config``: the ``pyramid.config.Configurator`` object.
    """
    config.add_route('ogcproxy', '/ogcproxy')
    config.add_view('pywpsproxy.ogcproxy.views:ogcproxy', route_name='ogcproxy')

def includeme(config):
    """ The callable making it possible to include papyrus_ogcproxy
    in a Pyramid application.

    Calling ``config.include(pywpsproxy.ogcproxy)`` will result in this
    callable being called.

    Arguments:

    * ``config``: the ``pyramid.config.Configurator`` object.
    """
    add_view(config)

