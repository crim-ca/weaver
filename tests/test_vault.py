import tempfile
import uuid

import pytest

from weaver.datatype import VaultFile
from weaver.vault.utils import parse_vault_token

VAULT_FAKE_TOKEN = VaultFile("").token
VAULT_FAKE_UUID1 = str(uuid.uuid4())
VAULT_FAKE_UUID2 = str(uuid.uuid4())


@pytest.mark.vault
@pytest.mark.parametrize("header,unique,expected", [
    (f"Basic {VAULT_FAKE_TOKEN}  ", True,
     {}),
    (f"Basic {VAULT_FAKE_TOKEN}  ", False,
     {}),
    ("token bad", True,
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


@pytest.mark.vault
def test_encrypt_decrypt():
    vault_file = VaultFile("")
    assert isinstance(vault_file.secret, bytes) and len(vault_file.secret)
    data = "SOME DUMMY DATA TO ENCRYPT"
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w+") as tmp_file:
        tmp_file.write(data)
        enc_file = vault_file.encrypt(tmp_file)
    enc_file.seek(0)
    enc_data = enc_file.read()
    assert isinstance(enc_data, bytes) and len(enc_data)
    assert enc_data != data
    dec_file = vault_file.decrypt(enc_file)
    dec_file.seek(0)
    dec_data = dec_file.read()
    assert isinstance(dec_data, bytes) and len(dec_data)
    assert dec_data.decode("utf-8") == data
