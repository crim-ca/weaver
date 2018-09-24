CRIM_ADES = 'crim-ades'
CRIM_EMS = 'crim-ems'
LOCALHOST = 'localhost'

KNOWN_DATA_SOURCES = frozenset([
    CRIM_ADES,
    CRIM_EMS,
])


# TODO: register data sources mapping to url in database
DATA_SOURCE_MAPPING = {
    LOCALHOST: 'https://localhost:5000',
    CRIM_ADES: 'https://ogc-ems.crim.ca/twitcher',
    CRIM_EMS: 'https://ogc-ades.crim.ca/twitcher',
    # TODO: other sources here
}


def retrieve_data_source_url(data_source):
    if data_source in KNOWN_DATA_SOURCES:
        return DATA_SOURCE_MAPPING[data_source]
    if data_source is not None:
        return data_source
    return DATA_SOURCE_MAPPING[LOCALHOST]
