"""
Admin interface for pyproxy
"""

from pyramid.config import Configurator

def includeme(config):
    """ The callable makes it possible to include admin
    in a Pyramid application.

    Calling ``config.include(pywpsproxy.admin)`` will result in this
    callable being called.

    Arguments:

    * ``config``: the ``pyramid.config.Configurator`` object.
    """
    config.add_route('create_token', '/admin/create_token')

