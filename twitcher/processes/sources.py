from urlparse import urlparse

CRIM_ADES = 'crim-ades'
CRIM_EMS = 'crim-ems'
LOCALHOST = 'localhost'
LOCALHOST_ADES = 'localhost-ades'

KNOWN_DATA_SOURCES = frozenset([
    CRIM_ADES,
    CRIM_EMS,
    LOCALHOST_ADES
])

CRIM_ADES_NETLOC = 'crim-ades.crim.ca'
CRIM_EMS_NETLOC = 'crim-ems.crim.ca'
LOCALHOST_NETLOC = 'localhost'
LOCALHOST_ADES_NETLOC = '10.30.90.187'

KNOWN_DATA_NETLOC = frozenset([
    CRIM_ADES_NETLOC,
    CRIM_EMS_NETLOC,
    LOCALHOST_NETLOC,
    LOCALHOST_ADES_NETLOC
])

# TODO: register data sources mapping to url in database
DATA_SOURCE_MAPPING = {
    LOCALHOST: 'https://localhost:5000',
    LOCALHOST_ADES: 'https://10.30.90.187:5001',
    CRIM_ADES: 'https://ogc-ems.crim.ca/twitcher',
    CRIM_EMS: 'https://ogc-ades.crim.ca/twitcher',
    # TODO: other sources here
}

DATA_NETLOC_MAPPING = {
    LOCALHOST_NETLOC: LOCALHOST,
    LOCALHOST_ADES_NETLOC: LOCALHOST_ADES,
    CRIM_EMS_NETLOC: CRIM_EMS,
    CRIM_ADES_NETLOC: CRIM_ADES,
    # TODO: other sources here
}


def retrieve_data_source_url(data_source):
    if data_source in KNOWN_DATA_SOURCES:
        return DATA_SOURCE_MAPPING[data_source]
    if data_source is not None:
        return data_source
    return DATA_SOURCE_MAPPING[LOCALHOST]


def get_data_source_from_url(data_url):
    try:
        o = urlparse(data_url)
        if o.netloc in KNOWN_DATA_NETLOC:
            return DATA_NETLOC_MAPPING[o.netloc]
    except Exception as exc:
        pass
    return LOCALHOST_ADES