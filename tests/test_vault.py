import uuid

import pytest

from weaver.datatype import VaultFile
from weaver.vault.utils import parse_vault_token


VAULT_FAKE_TOKEN = VaultFile("").token
VAULT_FAKE_UUID1 = str(uuid.uuid4())
VAULT_FAKE_UUID2 = str(uuid.uuid4())


@pytest.mark.parametrize("header,unique,expected", [
    (f"Basic {VAULT_FAKE_TOKEN}  ", True,
     {}),
    (f"Basic {VAULT_FAKE_TOKEN}  ", False,
     {}),
    (f"token bad", True,
     {}),
    (f" token  {VAULT_FAKE_TOKEN}  ", True,
     {None: VAULT_FAKE_TOKEN}),
    (f"token {VAULT_FAKE_TOKEN}", True,
     {None: VAULT_FAKE_TOKEN}),
    (f"token {VAULT_FAKE_TOKEN};", True,
     {None: VAULT_FAKE_TOKEN}),
    (f"token {VAULT_FAKE_TOKEN} ;id= ", True,  # even if unique doesn't require 'id', it must be valid if provided
     {}),
    (f"token {VAULT_FAKE_TOKEN} ;id=bad", True,  # even if unique doesn't require 'id', it must be valid if provided
     {}),
    (f"token {VAULT_FAKE_TOKEN} ;id={VAULT_FAKE_UUID1}", True,
     {VAULT_FAKE_UUID1: VAULT_FAKE_TOKEN}),
    (f"token {VAULT_FAKE_TOKEN} ; id = {VAULT_FAKE_UUID1}", True,  # no recommended but supported
     {VAULT_FAKE_UUID1: VAULT_FAKE_TOKEN}),
    (f"token {VAULT_FAKE_TOKEN} ; id = {VAULT_FAKE_UUID1},", True,
     {}),
    (f"token {VAULT_FAKE_TOKEN} ;id=\"{VAULT_FAKE_UUID1}\"", True,  # optional quotes
     {VAULT_FAKE_UUID1: VAULT_FAKE_TOKEN}),
    (f"token {VAULT_FAKE_TOKEN} ,", True,
     {}),
    (f"token {VAULT_FAKE_TOKEN} ,", False,
     {}),
    (f"token {VAULT_FAKE_TOKEN}", False,
     {}),
    (f"token {VAULT_FAKE_TOKEN}; id={VAULT_FAKE_UUID1}", False,
     {VAULT_FAKE_UUID1: VAULT_FAKE_TOKEN}),
    (f"token {VAULT_FAKE_TOKEN}; id={VAULT_FAKE_UUID1},", False,  # comma means many, so invalid when expecting unique
     {}),
    # perfectly well formatted tokens but with duplicate entries are not allowed
    (f"token {VAULT_FAKE_TOKEN}; id={VAULT_FAKE_UUID1},token {VAULT_FAKE_TOKEN}; id={VAULT_FAKE_UUID1}", False,
     {}),
    # partially well formed tokens makes all of them invalid
    # This is to ensure that requests that require many tokens don't partially succeed,
    # since the whole process will fail anyway. Also ensures that not only partial files get wiped after download.
    (f"token {VAULT_FAKE_TOKEN}; id={VAULT_FAKE_UUID1},token bad; id={VAULT_FAKE_UUID1}", False,
     {}),
    # properly formed tokens with no duplicates IDs, no restriction about duplicate tokens themselves (though unlikely)
    (f"token {VAULT_FAKE_TOKEN}; id={VAULT_FAKE_UUID1},token {VAULT_FAKE_TOKEN}; id={VAULT_FAKE_UUID2}", False,
     {VAULT_FAKE_UUID1: VAULT_FAKE_TOKEN, VAULT_FAKE_UUID2: VAULT_FAKE_TOKEN}),
    (f"token {VAULT_FAKE_TOKEN}; id={VAULT_FAKE_UUID1},token {VAULT_FAKE_TOKEN[:-3]}123; id={VAULT_FAKE_UUID2}", False,
     {VAULT_FAKE_UUID1: VAULT_FAKE_TOKEN, VAULT_FAKE_UUID2: VAULT_FAKE_TOKEN[:-3] + "123"}),
    # many tokens for endpoint expecting only one fails immediately regardless of contents
    # use valid format to make sure it fails because of the multi-token aspect
    (f"token {VAULT_FAKE_TOKEN}; id={VAULT_FAKE_UUID1},token {VAULT_FAKE_TOKEN}; id={VAULT_FAKE_UUID2}", True,
     {})
])
def test_parse_vault_token(header, unique, expected):
    result = parse_vault_token(header, unique=unique)
    assert result == expected
