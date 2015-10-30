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

    def __init__(self, url="https://localhost:38083/api/xmlrpc"):
        self.url = url

        
    def create_server(self, verify=True):
        context = _create_https_context(verify=verify)
        server = xmlrpclib.ServerProxy(self.url, context=context)
        return server
        

    def create_parser(self):
        parser = argparse.ArgumentParser(
            prog="twitcherctl",
            usage='''twitcherctl [<options>] <command> [<args>]''',
            description='twitcherctl -- control twitcher proxy service from the cmd line.',
            )
        parser.add_argument("--debug",
                            help="enable debug mode.",
                            action="store_true")
        parser.add_argument("--no-check-certificate",
                            help="don't validate the server's certificate.",
                            action="store_true")

        return parser

    def run(self, args):
        if args.debug:
            logger.setLevel(logging.DEBUG)

        server = self.create_server()
        return None

def main():
    logger.setLevel(logging.INFO)

    ctl = TwitcherCtl()
    parser = ctl.create_parser()
    argcomplete.autocomplete(parser)

    args = parser.parse_args()
    ctl.run(args)

if __name__ == '__main__':
    sys.exit(main())
