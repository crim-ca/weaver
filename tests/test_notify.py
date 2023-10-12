import contextlib
import os
import pathlib
import smtplib
import tempfile
import uuid

import mock
import pytest

from weaver import WEAVER_MODULE_DIR
from weaver.datatype import Job
from weaver.notify import decrypt_email, encrypt_email, notify_job_email, resolve_email_template
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


def test_notify_email_job_complete():
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
        notify_job_email(test_job, notify_email, settings)
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
        notify_job_email(test_job, notify_email, settings)
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


def test_notify_job_email_custom_template():
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
            notify_job_email(test_job, notify_email, settings)

        message_encoded = mock_smtp.return_value.sendmail.call_args[0][2]
        message = message_encoded.decode("utf8")
        assert message == "\n".join([
            "From: Weaver",
            f"To: {notify_email}",
            f"Subject: Job {test_job.process} {Status.SUCCEEDED}",
            "",
            f"Job: {test_url}/processes/{test_job.process}/jobs/{test_job.id}",
        ])


@pytest.mark.parametrize(
    ["settings", "test_process", "test_status", "tmp_default", "expect_result"],
    [
        ({}, None, None, None, 4),
        # directory exists, but none of the supported mako variants found under it
        ({"weaver.wps_email_notify_template_dir": tempfile.gettempdir()}, None, None, None, IOError),
        ({"weaver.wps_email_notify_template_dir": "/DOES_NOT_EXIST"}, None, None, None, 4),
        ({"weaver.wps_email_notify_template_dir": "<TMP_DIR>"}, None, None, None, 4),
        ({"weaver.wps_email_notify_template_dir": "<TMP_DIR>",
          "weaver.wps_email_notify_template_default": "RANDOM"}, None, None, None, 4),
        ({"weaver.wps_email_notify_template_dir": "<TMP_DIR>"}, None, None, None, 4),
        ({"weaver.wps_email_notify_template_dir": "<TMP_DIR>",
          "weaver.wps_email_notify_template_default": "test-default.mako"}, None, None, "random.mako", 4),
        ({"weaver.wps_email_notify_template_dir": "<TMP_DIR>"}, None, None, "test-default.mako", 4),
        ({"weaver.wps_email_notify_template_dir": "<TMP_DIR>"}, None, None, "test-default.mako", 4),
        ({"weaver.wps_email_notify_template_dir": "<TMP_DIR>",
          "weaver.wps_email_notify_template_default": "test-default.mako"}, None, None, "default.mako", 3),
        ({"weaver.wps_email_notify_template_dir": "<TMP_DIR>",
          "weaver.wps_email_notify_template_default": "test-default.mako"}, None, None, "test-default.mako", 2),
        (
            {"weaver.wps_email_notify_template_dir": "<TMP_DIR>",
             "weaver.wps_email_notify_template_default": "test-default.mako"},
            "random-process",
            None,
            "test-default.mako",
            2
        ),
        (
            {"weaver.wps_email_notify_template_dir": "<TMP_DIR>",
             "weaver.wps_email_notify_template_default": "test-default.mako"},
            "random-process",
            Status.SUCCEEDED,
            "test-default.mako",
            2
        ),
        (
            {"weaver.wps_email_notify_template_dir": "<TMP_DIR>",
             "weaver.wps_email_notify_template_default": "test-default.mako"},
            "tmp-process",
            Status.STARTED,
            "test-default.mako",
            2
        ),
        (
            {"weaver.wps_email_notify_template_dir": "<TMP_DIR>",
             "weaver.wps_email_notify_template_default": "test-default.mako"},
            "tmp-process",
            None,
            "test-default.mako",
            2
        ),
        (
            {"weaver.wps_email_notify_template_dir": "<TMP_DIR>",
             "weaver.wps_email_notify_template_default": "test-default.mako"},
            "tmp-process",
            Status.SUCCEEDED,
            "test-default.mako",
            2
        ),
        (
            {"weaver.wps_email_notify_template_dir": "<TMP_DIR>",
             "weaver.wps_email_notify_template_default": "test-default.mako"},
            "tmp-process",
            Status.STARTED,
            "test-default.mako",
            1
        ),
    ]
)
def test_resolve_email_template(settings, test_process, test_status, tmp_default, expect_result):
    # process name and job status important to evaluate expected mako file resolution
    tmp_process = "tmp-process"
    tmp_status = Status.STARTED

    with contextlib.ExitStack() as tmp_stack:
        tmp_dir = pathlib.Path(tmp_stack.enter_context(tempfile.TemporaryDirectory()))
        if settings.get("weaver.wps_email_notify_template_dir") == "<TMP_DIR>":
            settings["weaver.wps_email_notify_template_dir"] = tmp_dir

        tmp_proc_dir = tmp_dir / tmp_process
        os.makedirs(tmp_proc_dir, exist_ok=True)
        tmp_file0 = tmp_proc_dir / f"{tmp_process}.mako"
        tmp_file0.touch()
        tmp_file1 = tmp_dir / f"{tmp_status}.mako"
        tmp_file1.touch()
        tmp_file2 = tmp_dir / f"{tmp_default}.mako"
        tmp_file3 = tmp_dir / "default.mako"
        default_file = os.path.join(WEAVER_MODULE_DIR, "wps_restapi/templates/notification_email_example.mako")

        ordered_possible_matches = [
            tmp_file0,  # {tmp_dir}/{process}/{status}.mako
            tmp_file1,  # {tmp_dir}/{process}.mako
            tmp_file2,  # {tmp_dir}/{default}.mako
            tmp_file3,  # {tmp_dir}/default.mako
            default_file,  # weaver default mako
        ]

        test_job = Job(task_id=uuid.uuid4(), process=test_process, status=test_status)
        try:
            found_template = resolve_email_template(test_job, settings)
            found_template_index = ordered_possible_matches.index(found_template.filename)
            assert isinstance(expect_result, int), f"Test expected to raise {expect_result} but did not raise."
            assert found_template_index == expect_result
        except Exception as exc:
            assert issubclass(expect_result, Exception), f"Test did not expect an error, but raised {exc!s}."
            assert isinstance(exc, expect_result), f"Test expected {expect_result}, but raised {exc!s} instead."
