import pytest

from notify import encrypt_email


def test_encrypt_email_valid():
    settings = {
        "weaver.wps_email_encrypt_salt": "salty-email",
    }
    email = encrypt_email("some@email.com", settings)
    assert email == u"a1724b030d999322e2ecc658453f992472c63867cd3cef3b3d829d745bd80f34"


def test_encrypt_email_raise():
    with pytest.raises(TypeError):
        encrypt_email("", {})
        pytest.fail("Should have raised for empty email")
    with pytest.raises(TypeError):
        encrypt_email(1, {})
        pytest.fail("Should have raised for wrong type")
    with pytest.raises(ValueError):
        encrypt_email("ok@email.com", {})
        pytest.fail("Should have raised for invalid/missing settings")
