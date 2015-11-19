import getpass
import argcomplete
import argparse
import xmlrpclib
import ssl

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

        
    def create_server(self, hostname="localhost", port=38083, verify_ssl=True, username=None, password=None):
        # TODO: build url
        if username:
            url = "https://%s:%s@%s:%s" % (username, password, hostname, port)
        else:
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
        parser.add_argument("-u", "--username",
                            action="store",
                            )
        parser.add_argument("-p", "--password",
                            action="store",
                            )
        parser.add_argument('--hostname',
                            default='localhost',
                            action="store",
                            )
        parser.add_argument('--port',
                            default=38083,
                            type=type(38083),
                            action="store",
                            )
        parser.add_argument("-x", "--no-check-certificate",
                            dest='verify_ssl',
                            help="don't validate the server's certificate.",
                            action="store_false")

        # commands
        subparsers = parser.add_subparsers(
            dest='cmd',
            title='command',
            description='List of available commands',
            #help='Run "birdy <command> -h" to get additional help.'
            )

        # token
        # -----
        subparser = subparsers.add_parser('gentoken')
        

        # service registry
        # ----------------
        
        # list
        subparser = subparsers.add_parser('list')

        # clear
        subparser = subparsers.add_parser('clear')

        # register
        subparser = subparsers.add_parser('add')
        subparser.add_argument('--url',
                    dest='url',
                    required=True,
                    nargs=1,
                    default='http://localhost:8094/wps',
                    action="store",
                    #help="",
                    )

        # unregister
        subparser = subparsers.add_parser('remove')
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

        password = args.password
        if args.username:
            #username = raw_input('Username:')
            password = getpass.getpass(prompt='Password:')
            
        server = self.create_server(
            hostname=args.hostname, port=args.port, verify_ssl=args.verify_ssl,
            username=args.username, password=password)
        result = None
        try:
            if args.cmd == 'list':
                result = server.listServices()
            elif args.cmd == 'add':
                result = server.addService(args.url[0])
            elif args.cmd == 'remove':
                result = server.removeService(args.name[0])
            elif args.cmd == 'clear':
                result = server.clearServices()
            elif args.cmd == 'gentoken':
                result = server.generateToken()
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
