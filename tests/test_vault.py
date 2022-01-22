import uuid

import pytest

from weaver.datatype import VaultFile
from weaver.vault.utils import parse_vault_token


VAULT_FAKE_TOKEN = VaultFile("").token
VAULT_FAKE_UUID = str(uuid.uuid4())


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
    (f"token {VAULT_FAKE_TOKEN} ;id= ", True,
     {None: VAULT_FAKE_TOKEN}),
    (f"token {VAULT_FAKE_TOKEN} ;id=bad", True,
     {}),
    (f"token {VAULT_FAKE_TOKEN} ;id={VAULT_FAKE_UUID}", True,
     {VAULT_FAKE_UUID: VAULT_FAKE_TOKEN}),
    (f"token {VAULT_FAKE_TOKEN} ; id = {VAULT_FAKE_UUID}", True,
     {VAULT_FAKE_UUID: VAULT_FAKE_TOKEN}),
    (f"token {VAULT_FAKE_TOKEN} ; id = {VAULT_FAKE_UUID},", True,
     {}),
    (f"token {VAULT_FAKE_TOKEN} ,", True,
     {}),
    (f"token {VAULT_FAKE_TOKEN} ,", False,
     {}),
    (f"token {VAULT_FAKE_TOKEN}", False,
     {}),
    (f"token {VAULT_FAKE_TOKEN}; id={VAULT_FAKE_UUID}", False,
     {VAULT_FAKE_UUID: VAULT_FAKE_TOKEN}),
    (f"token {VAULT_FAKE_TOKEN}; id={VAULT_FAKE_UUID},", False,
     {VAULT_FAKE_UUID: VAULT_FAKE_TOKEN}),
    (f"token {VAULT_FAKE_TOKEN}; id={VAULT_FAKE_UUID},token {VAULT_FAKE_TOKEN}; id={VAULT_FAKE_UUID}", False,
     {}),
    (f"token {VAULT_FAKE_TOKEN}; id={VAULT_FAKE_UUID},token bad; id={VAULT_FAKE_UUID}", False,
     {VAULT_FAKE_UUID: VAULT_FAKE_TOKEN}),
])
def test_parse_vault_token(header, unique, expected):
    result = parse_vault_token(header, unique=unique)
    assert result == expected
