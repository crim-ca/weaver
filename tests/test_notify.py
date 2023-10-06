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

    # although encrypted are all different, they should all decrypt back to the original!
    email1 = decrypt_email(token1, settings)
    email2 = decrypt_email(token2, settings)
    email3 = decrypt_email(token3, settings)
    assert email1 == email2 == email3 == email


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
    test_url = "https://test-weaver.example.com"
    settings = {
        "weaver.url": test_url,
        "weaver.wps_email_notify_smtp_host": "xyz.test.com",
        "weaver.wps_email_notify_from_addr": "test-weaver@email.com",
        "weaver.wps_email_notify_password": "super-secret",
        "weaver.wps_email_notify_port": 12345,
        "weaver.wps_email_notify_timeout": 1,  # quick fail if invalid
    }
    notify_email = "test-user@email.com"
    test_job = Job(
        task_id=uuid.uuid4(),
        process="test-process",
        settings=settings,
    )
    test_job_err_url = f"{test_url}/processes/{test_job.process}/jobs/{test_job.id}/exceptions"
    test_job_out_url = f"{test_url}/processes/{test_job.process}/jobs/{test_job.id}/results"
    test_job_log_url = f"{test_url}/processes/{test_job.process}/jobs/{test_job.id}/logs"

    with mock.patch("smtplib.SMTP_SSL", autospec=smtplib.SMTP_SSL) as mock_smtp:
        mock_smtp.return_value.sendmail.return_value = None  # sending worked

        test_job.status = Status.SUCCEEDED
        notify_job_complete(test_job, notify_email, settings)
        mock_smtp.assert_called_with("xyz.test.com", 12345, timeout=1)
        assert mock_smtp.return_value.sendmail.call_args[0][0] == "test-weaver@email.com"
        assert mock_smtp.return_value.sendmail.call_args[0][1] == notify_email
        message_encoded = mock_smtp.return_value.sendmail.call_args[0][2]
        assert message_encoded
        message = message_encoded.decode("utf8")
        assert "From: Weaver" in message
        assert f"To: {notify_email}" in message
        assert f"Subject: Job {test_job.process} Succeeded"
        assert test_job_out_url in message
        assert test_job_log_url in message
        assert test_job_err_url not in message

        test_job.status = Status.FAILED
        notify_job_complete(test_job, notify_email, settings)
        assert mock_smtp.return_value.sendmail.call_args[0][0] == "test-weaver@email.com"
        assert mock_smtp.return_value.sendmail.call_args[0][1] == notify_email
        message_encoded = mock_smtp.return_value.sendmail.call_args[0][2]
        assert message_encoded
        message = message_encoded.decode("utf8")
        assert "From: Weaver" in message
        assert f"To: {notify_email}" in message
        assert f"Subject: Job {test_job.process} Failed"
        assert test_job_out_url not in message
        assert test_job_log_url in message
        assert test_job_err_url in message


def test_notify_job_complete_custom_template():
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".mako") as email_template_file:
        email_template_file.writelines([
            "From: Weaver\n",
            "To: ${to}\n",
            "Subject: Job ${job.process} ${job.status}\n",
            "\n",  # end of email header, content below
            "Job: ${job.status_url(settings)}\n",
        ])
        email_template_file.flush()
        email_template_file.seek(0)

        mako_dir, mako_name = os.path.split(email_template_file.name)
        test_url = "https://test-weaver.example.com"
        settings = {
            "weaver.url": test_url,
            "weaver.wps_email_notify_smtp_host": "xyz.test.com",
            "weaver.wps_email_notify_from_addr": "test-weaver@email.com",
            "weaver.wps_email_notify_password": "super-secret",
            "weaver.wps_email_notify_port": 12345,
            "weaver.wps_email_notify_timeout": 1,  # quick fail if invalid
            "weaver.wps_email_notify_template_dir": mako_dir,
            "weaver.wps_email_notify_template_default": mako_name,
        }
        notify_email = "test-user@email.com"
        test_job = Job(
            task_id=uuid.uuid4(),
            process="test-process",
            status=Status.SUCCEEDED,
            settings=settings,
        )

        with mock.patch("smtplib.SMTP_SSL", autospec=smtplib.SMTP_SSL) as mock_smtp:
            mock_smtp.return_value.sendmail.return_value = None  # sending worked
            notify_job_complete(test_job, notify_email, settings)

        message_encoded = mock_smtp.return_value.sendmail.call_args[0][2]
        message = message_encoded.decode("utf8")
        assert message == "\n".join([
            "From: Weaver",
            f"To: {notify_email}",
            f"Subject: Job {test_job.process} {Status.SUCCEEDED}",
            "",
            f"Job: {test_url}/processes/{test_job.process}/jobs/{test_job.id}",
        ])
