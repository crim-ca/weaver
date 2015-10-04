import pymongo

import logging
logger = logging.getLogger(__name__)

def mongodb(registry):
    settings = registry.settings
    return pymongo.Connection(settings['mongodb.url'])[settings['mongodb.db_name']]

    





