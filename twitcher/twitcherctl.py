import xmlrpclib
import ssl

import argcomplete
import argparse

import logging
logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.WARN)
logger = logging.getLogger(__name__)


def _create_https_context(verify=True):
    context = ssl._create_default_https_context()
    if verify == False:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context

class TwitcherCtl(object):

    def __init__(self):
        pass

        
    def create_server(self, hostname="localhost", port=38083, verify_ssl=True):
        # TODO: build url
        url = "https://%s:%s" % (hostname, port)
        context = _create_https_context(verify=verify_ssl)
        server = xmlrpclib.ServerProxy(url, context=context)
        return server
        

    def create_parser(self):
        parser = argparse.ArgumentParser(
            prog="twitcherctl",
            description='twitcherctl -- control twitcher proxy service from the cmd line.',
            )
        parser.add_argument("--debug",
                            help="enable debug mode.",
                            action="store_true")
        parser.add_argument("--no-check-certificate",
                            dest='verify_ssl',
                            help="don't validate the server's certificate.",
                            action="store_false")
        parser.add_argument('--hostname',
                            default='localhost',
                            action="store",
                            )
        parser.add_argument('--port',
                            default=38083,
                            type=type(38083),
                            action="store",
                            )

        # commands
        subparsers = parser.add_subparsers(
            dest='cmd',
            title='command',
            description='List of available commands',
            #help='Run "birdy <command> -h" to get additional help.'
            )

        # list
        subparser = subparsers.add_parser('list')

        # clear
        subparser = subparsers.add_parser('clear')

        # register
        subparser = subparsers.add_parser('register')
        subparser.add_argument('--url',
                    dest='url',
                    required=True,
                    nargs=1,
                    default='http://localhost:8094/wps',
                    action="store",
                    #help="",
                    )

        # unregister
        subparser = subparsers.add_parser('unregister')
        subparser.add_argument('--name',
                    dest='name',
                    required=True,
                    nargs=1,
                    action="store",
                    #help="",
                    )


        return parser

    def run(self, args):
        if args.debug:
            logger.setLevel(logging.DEBUG)

        if not args.verify_ssl:
            logger.warn('disabled certificate verification!')
            
        server = self.create_server(hostname=args.hostname, port=args.port, verify_ssl=args.verify_ssl)
        result = None
        if args.cmd == 'list':
            result = server.list()
        elif args.cmd == 'register':
            logger.debug('register %s', args.url[0])
            result = server.register(args.url[0])
        elif args.cmd == 'unregister':
            logger.debug('unregister %s', args.name[0])
            result = server.unregister(args.name[0])
        if args.cmd == 'clear':
            result = server.clear()
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
