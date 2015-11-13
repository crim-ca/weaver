from datetime import datetime
import pytz
from urlparse import urlparse

def now():
    return localize_datetime(datetime.utcnow())

def localize_datetime(dt, tz_name='UTC'):
    """Provide a timzeone-aware object for a given datetime and timezone name
    """
    assert dt.tzinfo == None
    utc = pytz.timezone('UTC')
    aware = utc.localize(dt)
    timezone = pytz.timezone(tz_name)
    tz_aware_dt = aware.astimezone(timezone)
    return tz_aware_dt

def baseurl(url):
    """
    return baseurl of given url
    """
    parsed_url = urlparse(url)
    if not parsed_url.netloc or not parsed_url.scheme in ("http", "https"):
        raise ValueError('bad url')
    service_url = "%s://%s%s" % (parsed_url.scheme, parsed_url.netloc, parsed_url.path.strip())
    return service_url
