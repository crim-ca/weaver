import argcomplete
import argparse

import logging
logging.basicConfig(format='%(levelname)s:%(message)s', level=logging.WARN)
logger = logging.getLogger(__name__)

class TwitcherCtl(object):

    def create_parser(self):
        parser = argparse.ArgumentParser(
            prog="twitcherctl",
            usage='''twitcherctl [<options>] <command> [<args>]''',
            description='twitcherctl -- control twitcher proxy service from the cmd line.',
            )
        parser.add_argument("--debug",
                            help="enable debug mode",
                            action="store_true")

        return parser

    def run(self, args):
        if args.debug:
            logger.setLevel(logging.DEBUG)
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
