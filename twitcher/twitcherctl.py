import getpass
import argcomplete
import argparse
import xmlrpclib
import ssl
from urlparse import urlparse

import logging
logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.WARN)
logger = logging.getLogger(__name__)


def _create_https_context(verify=True):
    context = ssl._create_default_https_context()
    if verify is False:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


def _create_server(url, verify_ssl=True, username=None, password=None):
    # TODO: disable basicauth when username is not set
    username = username or 'nouser'
    password = password or 'nopass'

    parsed = urlparse(url)
    url = "%s://%s:%s@%s%s" % (parsed.scheme, username, password, parsed.netloc, parsed.path)
    context = _create_https_context(verify=verify_ssl)
    server = xmlrpclib.ServerProxy(url, context=context)
    return server


class TwitcherCtl(object):
    """
    Command line to interact with the xmlrpc interface of the ``twitcher`` service.
    """

    def create_parser(self):
        parser = argparse.ArgumentParser(
            prog="twitcherctl",
            description='twitcherctl -- control twitcher service from the cmd line.',
        )
        parser.add_argument("--debug",
                            help="Enable debug mode.",
                            action="store_true")
        parser.add_argument('-s', '--serverurl',
                            metavar='URL',
                            default='https://localhost:38083',
                            help='URL on which twitcher server is listening (default "https://localhost:38083").')
        parser.add_argument("-u", "--username",
                            help="Username to use for authentication with server.")
        parser.add_argument("-p", "--password",
                            help="Password to use for authentication with server")
        parser.add_argument("-k", "--insecure",  # like curl
                            help="Don't validate the server's certificate.",
                            action="store_true")

        # commands
        subparsers = parser.add_subparsers(
            dest='cmd',
            title='command',
            description='List of available commands',
        )

        # token
        # -----
        subparser = subparsers.add_parser('gentoken', help="Generates an access token.")
        subparser.add_argument('-H', '--valid-in-hours', type=int, default=1,
                               help="Set how long the token is valid in hours (default: 1 hour).")
        subparser.add_argument('-e', '--env', nargs='*', default=[],
                               help="Set environment variable (key=value).")

        subparser = subparsers.add_parser('revoke', help="Removes given access token.")
        subparser.add_argument('token', help="access token")

        subparser = subparsers.add_parser('clean', help="Removes all access tokens.")

        # service registry
        # ----------------

        # status
        subparser = subparsers.add_parser('status', help="Lists all registered OWS services used by OWS proxy.")

        # purge
        subparser = subparsers.add_parser('purge', help="Removes all OWS services from the registry.")

        # register
        subparser = subparsers.add_parser('register',
                                          help="Adds OWS service to the registry to be used by the OWS proxy.")
        subparser.add_argument('url', help="Service url.")
        subparser.add_argument('--name', help="Service name. If not set then a name will be generated.")
        subparser.add_argument('--type', default='wps',
                               help="Service type (wps, wms). Default: wps.")
        subparser.add_argument('--public', action='store_true',
                               help="If set then service has no access restrictions.")

        # unregister
        subparser = subparsers.add_parser('unregister', help="Removes OWS service from the registry.")
        subparser.add_argument('name', help="Service name.")

        return parser

    def run(self, args):
        if args.debug:
            logger.setLevel(logging.DEBUG)

        if args.insecure:
            logger.warn('disabled certificate verification!')

        password = args.password
        if args.username:
            # username = raw_input('Username:')
            if not password:
                password = getpass.getpass(prompt='Password:')

        verify_ssl = args.insecure is False
        server = _create_server(
            url=args.serverurl, verify_ssl=verify_ssl,
            username=args.username, password=password)
        result = None
        try:
            if args.cmd == 'status':
                result = server.status()
            elif args.cmd == 'register':
                if args.name:
                    result = server.register(args.url, args.name, args.type, args.public)
                else:
                    result = server.register(args.url, None, args.type, args.public)
            elif args.cmd == 'unregister':
                result = server.unregister(args.name)
            elif args.cmd == 'purge':
                result = server.purge()
            elif args.cmd == 'gentoken':
                user_environ = {k: v for k, v in (x.split('=') for x in args.env)}
                result = server.gentoken(args.valid_in_hours, user_environ)
            elif args.cmd == 'revoke':
                result = server.revoke(args.token)
            elif args.cmd == 'clean':
                result = server.clean()
        except xmlrpclib.Fault as e:
            logger.error("A fault occurred: %s (%d)", e.faultString, e.faultCode)
        except xmlrpclib.ProtocolError as e:
            logger.error(
                "A protocol error occurred. URL: %s, HTTP/HTTPS headers: %s, Error code: %d, Error message: %s",
                e.url, e.headers, e.errcode, e.errmsg)
        except xmlrpclib.ResponseError as e:
            logger.error(
                "A response error occured. Maybe service needs authentication with username and password? %s",
                e.message)
        except Exception as e:
            logger.error(
                'Unknown error occured. \
                Maybe you need to use the "--insecure" option to access the service on HTTPS? \
                Is your service running and did you specify the correct service url (port)? \
                %s',
                e.message)
        else:
            return result


def main():
    logger.setLevel(logging.INFO)

    ctl = TwitcherCtl()
    parser = ctl.create_parser()
    argcomplete.autocomplete(parser)

    args = parser.parse_args()
    return ctl.run(args)

if __name__ == '__main__':
    sys.exit(main())
