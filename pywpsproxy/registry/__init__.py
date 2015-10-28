"""
registry for ows services
"""

from pyramid.config import Configurator

def includeme(config):
    """ The callable makes it possible to include admin
    in a Pyramid application.

    Calling ``config.include(pywpsproxy.registry)`` will result in this
    callable being called.

    Arguments:

    * ``config``: the ``pyramid.config.Configurator`` object.
    """
    config.add_route('add_service', '/registry/add')


