# MongoDB
# http://docs.pylonsproject.org/projects/pyramid-cookbook/en/latest/database/mongodb.html
# maybe use event to register mongodb

import pymongo

import logging
logger = logging.getLogger(__name__)


def mongodb(registry):
    settings = registry.settings
    client = pymongo.MongoClient(settings['mongodb.host'], int(settings['mongodb.port']))
    db = client[settings['mongodb.db_name']]
    db.services.create_index("name", unique=True)
    db.services.create_index("url", unique=True)
    return db


def includeme(config):
    config.registry.db = mongodb(config.registry)

    def _add_db(request):
        db = request.registry.db
        # if db_url.username and db_url.password:
        #     db.authenticate(db_url.username, db_url.password)
        return db
    config.add_request_method(_add_db, 'db', reify=True)
