"""
Read or write data from or to local memory.

Though not very valuable in a production setup, these store adapters are great
for testing purposes.
"""

from twitcher.store.base import AccessTokenStore
from twitcher.exceptions import AccessTokenNotFound


class MemoryTokenStore(AccessTokenStore):
    """
    Stores tokens in memory.
    Useful for testing purposes or APIs with a very limited set of clients.

    Use mongodb as storage to be able to scale.
    """
    def __init__(self):
        self.access_tokens = {}

    def save_token(self, access_token):
        self.access_tokens[access_token.token] = access_token
        return True

    def delete_token(self, token):
        if token in self.access_tokens:
            del self.access_tokens[token]

    def fetch_by_token(self, token):
        if token not in self.access_tokens:
            raise AccessTokenNotFound

        return self.access_tokens[token]

    def clean_tokens(self):
        self.access_tokens = {}
