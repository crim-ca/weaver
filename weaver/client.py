from six.moves.urllib.parse import urlparse
import six
import ssl
import logging
LOGGER = logging.getLogger("weaver")

if six.PY2:
    LOGGER.debug('Python 2.x')
    import xmlrpclib
else:
    LOGGER.debug('Python 3.x')
    import xmlrpc.client as xmlrpclib


def _create_https_context(verify=True):
    # noinspection PyProtectedMember
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
            LOGGER.error("A fault occurred: %s (%d)", e.faultString, e.faultCode)
            raise
        except xmlrpclib.ProtocolError as e:
            LOGGER.error(
                "A protocol error occurred. URL: %s, HTTP/HTTPS headers: %s, Error code: %d, Error message: %s",
                e.url, e.headers, e.errcode, e.errmsg)
            raise
        except xmlrpclib.ResponseError as e:
            LOGGER.error(
                "A response error occured. Maybe service needs authentication with username and password? %s",
                e.message)
            raise
        except Exception as e:
            LOGGER.error(
                " Unknown error occured. "
                "Maybe you need to use the \"--insecure\" option to access the service on HTTPS? "
                "Is your service running and did you specify the correct service url (port)? "
                "%s",
                e.message)
            raise
        else:
            return result
    return _handle_error


class WeaverService(object):
    def __init__(self, url, username=None, password=None, verify=True):
        self.server = _create_server(url, username=username, password=password, verify=verify)

    # service registry

    @xmlrpc_error_handler
    def register_service(self, url, data=None, overwrite=True):
        data = data or {}
        return self.server.register_service(url, data, overwrite)

    @xmlrpc_error_handler
    def unregister_service(self, name):
        return self.server.unregister_service(name)

    @xmlrpc_error_handler
    def list_services(self):
        return self.server.list_services()

    @xmlrpc_error_handler
    def clear_services(self):
        return self.server.clear_services()

    @xmlrpc_error_handler
    def get_service_by_url(self, url):
        return self.server.get_service_by_url(url)

    @xmlrpc_error_handler
    def get_service_by_name(self, name):
        return self.server.get_service_by_name(name)
