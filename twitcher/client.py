import xmlrpclib
import ssl
from urlparse import urlparse
from datetime import datetime


def _create_https_context(verify=True):
    context = ssl._create_default_https_context()
    if verify is False:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def _create_server(url, username=None, password=None, verify=True):
    # TODO: disable basicauth when username is not set
    username = username or 'nouser'
    password = password or 'nopass'

    parsed = urlparse(url)
    url = "%s://%s:%s@%s%s" % (parsed.scheme, username, password, parsed.netloc, parsed.path)
    context = _create_https_context(verify=verify)
    server = xmlrpclib.ServerProxy(url, context=context)
    return server


def xmlrpc_error_handler(wrapped):
    def _handle_error(*args, **kwargs):
        try:
            result = wrapped(*args, **kwargs)
        except xmlrpclib.Fault as e:
            logger.error("A fault occurred: %s (%d)", e.faultString, e.faultCode)
            raise
        except xmlrpclib.ProtocolError as e:
            logger.error(
                "A protocol error occurred. URL: %s, HTTP/HTTPS headers: %s, Error code: %d, Error message: %s",
                e.url, e.headers, e.errcode, e.errmsg)
            raise
        except xmlrpclib.ResponseError as e:
            logger.error(
                "A response error occured. Maybe service needs authentication with username and password? %s",
                e.message)
            raise
        except Exception as e:
            logger.error(
                'Unknown error occured. \
                Maybe you need to use the "--insecure" option to access the service on HTTPS? \
                Is your service running and did you specify the correct service url (port)? \
                %s',
                e.message)
            raise
        else:
            return result
    return _handle_error


class TwitcherService(object):
    def __init__(self, url, username=None, password=None, verify=True):
        self.server = _create_server(url, username=username, password=password, verify=verify)

    # tokens

    @xmlrpc_error_handler
    def gentoken(self, valid_in_hours=1, environ=None):
        environ = environ or {}
        return self.server.gentoken(valid_in_hours, environ)

    @xmlrpc_error_handler
    def revoke(self, token):
        return self.server.revoke(token=token)

    @xmlrpc_error_handler
    def clean(self):
        return self.server.clean()

    # service registry

    @xmlrpc_error_handler
    def register_service(self, url, name=None, service_type=None, public=False, c4i=False, overwrite=True):
        service_type = service_type or 'wps'
        if not name:
            name = None
        return self.server.register(url, name, service_type, public, c4i, overwrite)

    @xmlrpc_error_handler
    def unregister_service(self, name):
        return self.server.unregister(name)

    @xmlrpc_error_handler
    def status(self):
        return self.server.status()

    @xmlrpc_error_handler
    def clear_services(self):
        return self.server.clear_services()

    @xmlrpc_error_handler
    def is_public(self, name):
        return self.server.is_public(name)

    @xmlrpc_error_handler
    def get_service_name(self, url):
        return self.server.get_service_name(url)

    @xmlrpc_error_handler
    def get_service_by_url(self, url):
        return self.server.get_service_by_url(url)

    @xmlrpc_error_handler
    def get_service_by_name(self, name):
        return self.server.get_service_by_name(name)
