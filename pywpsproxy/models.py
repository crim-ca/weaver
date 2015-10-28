import pymongo

import logging
logger = logging.getLogger(__name__)

def mongodb(registry):
    settings = registry.settings
    client = pymongo.MongoClient(settings['mongodb.host'], int(settings['mongodb.port']))
    db = client[settings['mongodb.db_name']]
    db.services.create_index("identifier", unique=True)
    db.services.create_index("url", unique=True)
    return db


    





