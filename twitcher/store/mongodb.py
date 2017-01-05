"""
Store adapters to read/write data to from/to mongodb using pymongo.
"""

from twitcher.store import AccessTokenStore
from twitcher.tokens import AccessToken, AccessTokenNotFound


class MongodbStore(object):
    """
    Base class extended by all concrete store adapters.
    """

    def __init__(self, collection):
        self.collection = collection


class MongodbAccessTokenStore(AccessTokenStore, MongodbStore):
    def save_token(self, access_token):
        self.collection.insert_one(access_token)

    def delete_token(self, token):
        self.collection.delete_one({'token': token})

    def fetch_by_token(self, token):
        token = self.collection.find_one({'token': token})
        if not token:
            raise AccessTokenNotFound
        return AccessToken(token)

    def clean_tokens(self):
        self.collection.drop()
