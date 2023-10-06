import os
import smtplib
import tempfile
import uuid

import mock
import pytest

from weaver.datatype import Job
from weaver.notify import decrypt_email, encrypt_email, notify_job_complete
from weaver.status import Status


def test_encrypt_decrypt_email_valid():
    settings = {
        "weaver.wps_email_encrypt_salt": "salty-email",
    }
    email = "some@email.com"
    token = encrypt_email(email, settings)
    assert token != email
    value = decrypt_email(token, settings)
    assert value == email


def test_encrypt_email_random():
    email = "test@email.com"
    settings = {"weaver.wps_email_encrypt_salt": "salty-email"}
    token1 = encrypt_email(email, settings)
    token2 = encrypt_email(email, settings)
    token3 = encrypt_email(email, settings)
    assert token1 != token2 != token3


@pytest.mark.parametrize("email_func", [encrypt_email, decrypt_email])
def test_encrypt_decrypt_email_raise(email_func):
    with pytest.raises(TypeError):
        email_func("", {})
        pytest.fail("Should have raised for empty email")
    with pytest.raises(TypeError):
        email_func(1, {})  # type: ignore
        pytest.fail("Should have raised for wrong type")
    with pytest.raises(ValueError):
        email_func("ok@email.com", {})
        pytest.fail("Should have raised for invalid/missing settings")


def test_notify_job_complete():
    settings = {
        "weaver.url": "test-weaver.example.com",
        "weaver.wps_email_notify_smtp_host": "xyz.test.com",
        "weaver.wps_email_notify_from_addr": "test-weaver@email.com",
        "weaver.wps_email_notify_password": "super-secret",
        "weaver.wps_email_notify_port": 12345,
    }
    notify_email = "test-user@email.com"
    test_job = Job(
        task_id=uuid.uuid4(),
        process="test-process",
        settings=settings,
    )

    with mock.patch("smtplib.SMTP_SSL", autospec=smtplib.SMTP_SSL) as mock_smtp:
        mock_smtp.sendmail = mock.MagicMock(return_value=None)  # sending worked

        test_job.status = Status.SUCCEEDED
        test_job.progress = 100
        notify_job_complete(test_job, notify_email, settings)
        mock_smtp.assert_called_with("xyz.test.com", 12345)

        # test_job.status = Status.FAILED
        # test_job.progress = 42
        # notify_job_complete(test_job, notify_email, settings)


def test_notify_job_complete_custom_template():
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".mako") as email_template_file:
        mako_dir, mako_name = os.path.split(email_template_file.name)
        settings = {
            "weaver.url": "test-weaver.example.com",
            "weaver.wps_email_notify_smtp_host": "xyz.test.com",
            "weaver.wps_email_notify_from_addr": "test-weaver@email.com",
            "weaver.wps_email_notify_password": "super-secret",
            "weaver.wps_email_notify_port": 12345,
            "weaver.wps_email_notify_template_dir": mako_dir,
            "weaver.wps_email_notify_template_default": mako_name,
        }
        with mock.patch("smtplib.SMTP_SSL", autospec=smtplib.SMTP_SSL) as mock_smtp:
            mock_smtp.sendmail = mock.MagicMock(return_value=None)  # sending worked

        mock_smtp.ass
