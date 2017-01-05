"""
This python 2.x/3.x compatibility modules is based on the pywps 4.x code.
"""

import logging
import sys


LOGGER = logging.getLogger('twitcher')
PY2 = sys.version_info[0] == 2
PY3 = not PY2

if PY2:
    LOGGER.debug('Python 2.x')
    text_type = unicode  # noqa
    from StringIO import StringIO
    # from flufl.enum import Enum
    from urlparse import urlparse
    from urlparse import urljoin
    from urllib2 import urlopen
    import xmlrpclib
else:
    LOGGER.debug('Python 3.x')
    text_type = str
    from io import StringIO
    # from enum import Enum
    from urllib.parse import urlparse
    from urllib.parse import urljoin
    from urllib.request import urlopen
    import xmlrpc.client as xmlrpclib
