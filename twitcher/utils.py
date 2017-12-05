import time
from datetime import datetime
import pytz
from lxml import etree

from twitcher.exceptions import ServiceNotFound

from twitcher._compat import urlparse

import logging
logger = logging.getLogger(__name__)


def is_valid_url(url):
    try:
        parsed_url = urlparse(url)
        return True if all([parsed_url.scheme, ]) else False
    except Exception:
        return False


def parse_service_name(url):
    parsed_url = urlparse(url)
    service_name = None
    if parsed_url.path.startswith("/ows/proxy"):
        parts = parsed_url.path.strip('/').split('/')
        if len(parts) > 2:
            service_name = parts[2]
    if not service_name:
        raise ServiceNotFound
    return service_name


def now():
    return localize_datetime(datetime.utcnow())


def now_secs():
    """
    Return the current time in seconds since the Epoch.
    """
    return int(time.time())


def expires_at(hours=1):
    return now_secs() + hours * 3600


def localize_datetime(dt, tz_name='UTC'):
    """Provide a timzeone-aware object for a given datetime and timezone name
    """
    tz_aware_dt = dt
    if dt.tzinfo is None:
        utc = pytz.timezone('UTC')
        aware = utc.localize(dt)
        timezone = pytz.timezone(tz_name)
        tz_aware_dt = aware.astimezone(timezone)
    else:
        logger.warn('tzinfo already set')
    return tz_aware_dt


def baseurl(url):
    """
    return baseurl of given url
    """
    parsed_url = urlparse(url)
    if not parsed_url.netloc or parsed_url.scheme not in ("http", "https"):
        raise ValueError('bad url')
    service_url = "%s://%s%s" % (parsed_url.scheme, parsed_url.netloc, parsed_url.path.strip())
    return service_url


def path_elements(path):
    elements = [el.strip() for el in path.split('/')]
    elements = [el for el in elements if len(el) > 0]
    return elements


def lxml_strip_ns(tree):
    for node in tree.iter():
        try:
            has_namespace = node.tag.startswith('{')
        except AttributeError:
            continue  # node.tag is not a string (node is a comment or similar)
        if has_namespace:
            node.tag = node.tag.split('}', 1)[1]


def replace_caps_url(xml, url, prev_url=None):
    ns = {
        'ows': 'http://www.opengis.net/ows/1.1',
        'xlink': 'http://www.w3.org/1999/xlink'}
    doc = etree.fromstring(xml)
    # wms 1.1.1 onlineResource
    if 'WMT_MS_Capabilities' in doc.tag:
        logger.debug("replace proxy urls in wms 1.1.1")
        for element in doc.findall('.//OnlineResource[@xlink:href]', namespaces=ns):
            parsed_url = urlparse(element.get('{http://www.w3.org/1999/xlink}href'))
            new_url = url
            if parsed_url.query:
                new_url += '?' + parsed_url.query
            element.set('{http://www.w3.org/1999/xlink}href', new_url)
        xml = etree.tostring(doc)
    # wms 1.3.0 onlineResource
    elif 'WMS_Capabilities' in doc.tag:
        logger.debug("replace proxy urls in wms 1.3.0")
        for element in doc.findall('.//{http://www.opengis.net/wms}OnlineResource[@xlink:href]', namespaces=ns):
            parsed_url = urlparse(element.get('{http://www.w3.org/1999/xlink}href'))
            new_url = url
            if parsed_url.query:
                new_url += '?' + parsed_url.query
            element.set('{http://www.w3.org/1999/xlink}href', new_url)
        xml = etree.tostring(doc)
    # wps operations
    elif 'Capabilities' in doc.tag:
        for element in doc.findall('ows:OperationsMetadata//*[@xlink:href]', namespaces=ns):
            element.set('{http://www.w3.org/1999/xlink}href', url)
        xml = etree.tostring(doc)
    elif prev_url:
        xml = xml.decode('utf-8', 'ignore')
        xml = xml.replace(prev_url, url)
    return xml
