"""
This python 2.x/3.x compatibility modules is based on the pywps 4.x code.
"""

import logging
import sys
from six.moves.urllib.parse import urlparse, urljoin, parse_qs, parse_qsl
from six.moves.urllib.request import urlopen


LOGGER = logging.getLogger('twitcher')
PY2 = sys.version_info[0] == 2
PY3 = not PY2

from six.moves.urllib.parse import urlparse, urljoin, parse_qs, parse_qsl
from six.moves.urllib.request import urlopen
if PY2:
    LOGGER.debug('Python 2.x')
    text_type = unicode  # noqa
    from StringIO import StringIO
    import xmlrpclib
else:
    LOGGER.debug('Python 3.x')
    text_type = str
    from io import StringIO
    import xmlrpc.client as xmlrpclib
