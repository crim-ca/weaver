import os
import sys
import getpass
import argcomplete
import argparse

from weaver.client import WeaverService
from weaver.warning import DisabledSSLCertificateVerificationWarning

import warnings
import logging
LOGGER_LEVEL = os.getenv('weaver_LOGGER_LEVEL', logging.WARN)
logging.basicConfig(format='%(levelname)s:%(message)s', level=LOGGER_LEVEL)
LOGGER = logging.getLogger(__name__)


class weaverCtl(object):
    """
    Command line to interact with the xmlrpc interface of the ``weaver`` service.
    """

    @staticmethod
    def create_parser():
        parser = argparse.ArgumentParser(
            prog="weaverctl",
            description='weaverctl -- control weaver service from the cmd line.',
        )
        parser.add_argument("--debug",
                            help="Enable debug mode.",
                            action="store_true")
        parser.add_argument('-s', '--serverurl',
                            metavar='URL',
                            default='https://localhost:5000',
                            help='URL on which weaver server is listening (default "https://localhost:5000").')
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

        # service registry
        # ----------------

        # list
        subparser = subparsers.add_parser('list', help="Lists all registered OWS services used by OWS proxy.")

        # clear
        subparser = subparsers.add_parser('clear', help="Removes all OWS services from the registry.")

        # register
        subparser = subparsers.add_parser('register',
                                          help="Adds OWS service to the registry to be used by the OWS proxy.")
        subparser.add_argument('url', help="Service url.")
        subparser.add_argument('--name', help="Service name. If not set then a name will be generated.")
        subparser.add_argument('--type', default='wps',
                               help="Service type (wps, wms). Default: wps.")
        subparser.add_argument('--public', action='store_true',
                               help="If set then service has no access restrictions.")
        subparser.add_argument('--auth', default='token',
                               help="Authentication method (token, cert). Default: token.")

        # unregister
        subparser = subparsers.add_parser('unregister', help="Removes OWS service from the registry.")
        subparser.add_argument('name', help="Service name.")

        return parser

    @staticmethod
    def run(args):
        if args.debug:
            LOGGER.setLevel(logging.DEBUG)

        if args.insecure:
            warnings.warn("Disabled certificate verification!", DisabledSSLCertificateVerificationWarning)

        password = args.password
        if args.username:
            # username = raw_input('Username:')
            if not password:
                password = getpass.getpass(prompt='Password:')

        verify_ssl = args.insecure is False
        service = WeaverService(url=args.serverurl, username=args.username, password=password, verify=verify_ssl)
        result = None
        try:
            if args.cmd == 'list':
                result = service.list_services()
            elif args.cmd == 'register':
                result = service.register_service(
                    url=args.url,
                    data={'name': args.name, 'type': args.type, 'public': args.public, 'auth': args.auth})
            elif args.cmd == 'unregister':
                result = service.unregister_service(name=args.name)
            elif args.cmd == 'clear':
                result = service.clear_services()
        except Exception as e:
            LOGGER.error("Error: %s", e.message)
        else:
            LOGGER.info("Result: %s", result)
            return result


def main():
    LOGGER.setLevel(LOGGER_LEVEL)

    ctl = weaverCtl()
    parser = ctl.create_parser()
    argcomplete.autocomplete(parser)

    args = parser.parse_args()
    return ctl.run(args)


if __name__ == '__main__':
    sys.exit(main())
