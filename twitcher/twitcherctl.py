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
    if verify == False:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context

def _create_server(url, verify_ssl=True, username=None, password=None):
    if username:
        # TODO: build url
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
        parser.add_argument("-k", "--insecure", # like curl
                            dest='verify_ssl',
                            help="Don't validate the server's certificate.",
                            action="store_false")

        # commands
        subparsers = parser.add_subparsers(
            dest='cmd',
            title='command',
            description='List of available commands',
            )

        # token
        # -----
        subparser = subparsers.add_parser('gentoken', help="Generates an access token.")
        subparser.add_argument('-e', '--env', nargs='*', default=[], help="Set environment variable (key=value).")
        
        subparser = subparsers.add_parser('remove_token', help="Removes given access token.")
        subparser.add_argument('token', help="access token")
        
        subparser = subparsers.add_parser('clear_tokens', help="Removes all access tokens.")
        

        # service registry
        # ----------------
        
        # list
        subparser = subparsers.add_parser('list_services', help="Lists all registered OWS services for OWS proxy.")

        # clear
        subparser = subparsers.add_parser('clear_services', help="Removes all OWS services from the registry.")

        # register
        subparser = subparsers.add_parser('add_service', help="Adds a OWS service to the registry to be used by the OWS proxy.")
        subparser.add_argument('url', help="Service url.")
        subparser.add_argument('--name', help="Service name. If not set then a name will be generated.")

        # unregister
        subparser = subparsers.add_parser('remove_service', help="Removes OWS service from the registry.")
        subparser.add_argument('name', help="Service name.")

        return parser

    def run(self, args):
        if args.debug:
            logger.setLevel(logging.DEBUG)

        if not args.verify_ssl:
            logger.warn('disabled certificate verification!')

        password = args.password
        if args.username:
            #username = raw_input('Username:')
            password = getpass.getpass(prompt='Password:')
            
        server = _create_server(
            url=args.serverurl, verify_ssl=args.verify_ssl,
            username=args.username, password=password)
        result = None
        try:
            if args.cmd == 'list_services':
                result = server.list_services()
            elif args.cmd == 'add_service':
                if args.name:
                    result = server.add_service(args.url, args.name)
                else:
                    result = server.add_service(args.url)
            elif args.cmd == 'remove_service':
                result = server.remove_service(args.name)
            elif args.cmd == 'clear_services':
                result = server.clear_services()
            elif args.cmd == 'gentoken':
                user_environ = {k:v for k,v in (x.split('=') for x in args.env) }
                result = server.generate_token(user_environ)
            elif args.cmd == 'remove_token':
                result = server.remove_token(args.token)
            elif args.cmd == 'clear_tokens':
                result = server.clear_tokens()
        except xmlrpclib.Fault as e:
            logger.error("A fault occurred: %s (%d)", e.faultString, e.faultCode)
        except xmlrpclib.ProtocolError as e:
            logger.error("A protocol error occurred. URL: %s, HTTP/HTTPS headers: %s, Error code: %d, Error message: %s",  e.url, e.headers, e.errcode, e.errmsg)
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
