"""
Tests to validate that :mod:`celery` execution behaves as intended.
"""

# pylint: disable=R1729  # ignore non-generator representation employed for displaying test log results

import contextlib
import inspect
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest

from tests.utils import get_settings_from_testapp, get_test_weaver_app, setup_config_with_mongodb
from weaver.config import WeaverConfiguration
from weaver.database import get_db
from weaver.database.mongodb import get_mongodb_connection
from weaver.utils import retry_on_condition
from weaver.wps.utils import get_wps_url

if TYPE_CHECKING:
    from typing import Tuple

    from pymongo.collection import Collection


def is_attribute_none(exception):
    # type: (Exception) -> bool
    return isinstance(exception, AttributeError) and any(err in str(exception) for err in ["None", "NoneType"])


def get_taskmeta_output(taskmeta_collection, output):
    # type: (Collection, Tuple[str, str, str, int, str]) -> str
    task_id, stdout, stderr, returncode, worker_logfile = output
    taskmeta = taskmeta_collection.find_one({"_id": task_id})
    if taskmeta is None:
        with open(worker_logfile, encoding="utf-8") as log_file:
            worker_log = log_file.read()
        raise AttributeError(
            f"Celery taskmeta is None for task ID [{task_id}]. "
            f"Celery call exit code=[{returncode}], stdout=[{stdout}], stderr=[{stderr}]. "
            f"Worker log:\n{worker_log[-12000:]}"
        )
    if taskmeta.get("status") not in ["SUCCESS", "FAILURE", "REVOKED"]:
        raise AttributeError(
            f"Celery taskmeta is None or not terminal for task ID [{task_id}]. "
            f"status=[{taskmeta.get('status')}]"
        )
    return str(taskmeta.get("traceback") or "") + str(taskmeta.get("result") or "")


@pytest.mark.slow
@pytest.mark.functional
@pytest.mark.flaky(reruns=3, reruns_delay=1)
def test_celery_registry_resolution():
    """
    Tests that Celery worker processes resolve Weaver registry settings from their application configuration.
    """
    python_bin = sys.executable
    python_dir = os.path.dirname(python_bin)
    debug_path = os.path.expandvars(os.environ["PATH"])
    celery_bin = os.path.join(python_dir, "celery")

    config = setup_config_with_mongodb(settings={
        "weaver.configuration": WeaverConfiguration.HYBRID,
        "weaver.wps_output_url": "http://localhost/wps-outputs",
        "weaver.wps_output_dir": "/tmp/weaver-test/wps-outputs",  # nosec: B108 # don't care hardcoded for test
    })
    webapp = get_test_weaver_app(config=config)
    settings = get_settings_from_testapp(webapp)
    wps_url = get_wps_url(settings)
    job_store = get_db(settings).get_store("jobs")
    job1 = job_store.save_job(
        task_id="tmp", process="jsonarray2netcdf", inputs={"input": {"href": "http://random-dont-care.com/fake.json"}}
    )
    job2 = job_store.save_job(
        task_id="tmp", process="jsonarray2netcdf", inputs={"input": {"href": "http://random-dont-care.com/fake.json"}}
    )

    with contextlib.ExitStack() as stack:
        celery_db_name = f"celery-test-{uuid4().hex}"
        celery_mongo_broker = f"""mongodb://{settings["mongodb.host"]}:{settings["mongodb.port"]}/{celery_db_name}"""
        worker_dir = stack.enter_context(tempfile.TemporaryDirectory(prefix="weaver-celery-test-"))
        celery_logfile = os.path.join(worker_dir, "worker.log")
        subprocess_env = {
            "PATH": f"{python_dir}:{debug_path}",
            "PYTHONPATH": os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")),
        }
        cfg_ini = stack.enter_context(tempfile.NamedTemporaryFile(suffix=".ini", mode="w", encoding="utf-8"))
        cfg_ini.write(
            inspect.cleandoc(f"""
            [app:main]
            use = egg:crim-weaver
            mongodb.host = {settings["mongodb.host"]}
            mongodb.port = {settings["mongodb.port"]}
            mongodb.db_name = {settings["mongodb.db_name"]}
            weaver.configuration = HYBRID
            weaver.wps_output_url = {settings["weaver.wps_output_url"]}
            weaver.wps_output_dir = {settings["weaver.wps_output_dir"]}
            [celery]
            broker_url = {celery_mongo_broker}
            result_backend = {celery_mongo_broker}
            """)
        )
        cfg_ini.flush()
        cfg_ini.seek(0)

        celery_process = stack.enter_context(subprocess.Popen(
            [
                celery_bin,
                "-A",
                "pyramid_celery.celery_app",
                "worker",
                "-B",
                "-E",
                "--ini", cfg_ini.name,
                "--loglevel=DEBUG",
                "--time-limit", "10",
                "--soft-time-limit", "10",
                # following will cause an error on any subsequent task
                # if registry is not properly retrieved across processes/threads
                "--concurrency", "1",
                "--max-tasks-per-child", "1",
            ],
            universal_newlines=True,
            start_new_session=True,
            stdout=stack.enter_context(open(celery_logfile, mode="w", encoding="utf-8")),
            stderr=subprocess.STDOUT,
            env=subprocess_env,
        ))  # type: subprocess.Popen

        def stop_celery_worker():
            try:
                os.killpg(celery_process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            celery_process.wait(timeout=10)

        stack.callback(stop_celery_worker)
        worker_ready = False
        worker_log = ""
        inspect_output = ""
        for _ in range(30):
            with open(celery_logfile, encoding="utf-8") as log_file:
                worker_log = log_file.read()
            if celery_process.poll() is not None:
                raise AssertionError(
                    f"Celery worker exited with code [{celery_process.returncode}].\n{worker_log[-12000:]}"
                )
            inspect_ping = subprocess.run(
                [
                    celery_bin,
                    "-b", celery_mongo_broker,
                    "inspect", "ping",
                    "--timeout", "1",
                ],
                universal_newlines=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=subprocess_env,
                timeout=5,
                check=False,
            )
            inspect_output = inspect_ping.stdout + inspect_ping.stderr
            if inspect_ping.returncode == 0 and "pong" in inspect_output.lower():
                worker_ready = True
                break
            time.sleep(1)
        assert worker_ready, (
            f"Celery worker did not respond to inspect ping. "
            f"inspect output=[{inspect_output}]\n{worker_log[-12000:]}"
        )
        assert "Initiating weaver application" in worker_log
        assert "Celery runner detected." in worker_log

        celery_task_cmd1 = stack.enter_context(subprocess.Popen(
            [
                celery_bin,
                "-b", celery_mongo_broker,
                "call",
                "-a", json.dumps([str(job1.uuid), wps_url]),
                "weaver.processes.execution.execute_process",
            ],
            universal_newlines=True,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=subprocess_env,
        ))  # type: subprocess.Popen
        celery_task_cmd2 = stack.enter_context(subprocess.Popen(
            [
                celery_bin,
                "-b", celery_mongo_broker,
                "call",
                "-a", json.dumps([str(job2.uuid), wps_url]),
                "weaver.processes.execution.execute_process",
            ],
            universal_newlines=True,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=subprocess_env,
        ))  # type: subprocess.Popen

        task1_stdout, task1_stderr = retry_on_condition(
            lambda: celery_task_cmd1.communicate(),
            condition=is_attribute_none, retries=5, interval=1,
        )
        task2_stdout, task2_stderr = retry_on_condition(
            lambda: celery_task_cmd2.communicate(),
            condition=is_attribute_none, retries=5, interval=1,
        )
        task_outputs = [
            (celery_task_cmd1, task1_stdout, task1_stderr),
            (celery_task_cmd2, task2_stdout, task2_stderr),
        ]
        task_results = []
        for task_command, task_stdout, task_stderr in task_outputs:
            assert task_command.returncode == 0, (
                f"Celery call failed with exit code [{task_command.returncode}]. "
                f"stdout=[{task_stdout}], stderr=[{task_stderr}]"
            )
            try:
                task_id = str(UUID(task_stdout.strip()))
            except ValueError as exc:
                raise AssertionError(
                    f"Celery call did not return a task UUID. stdout=[{task_stdout}], stderr=[{task_stderr}]"
                ) from exc
            task_metadata = (task_id, task_stdout, task_stderr, task_command.returncode, celery_logfile)
            task_results.append(task_metadata)

        celery_mongo_db = get_mongodb_connection({
            "mongodb.host": settings["mongodb.host"],
            "mongodb.port": settings["mongodb.port"],
            "mongodb.db_name": celery_db_name,
        })
        celery_taskmeta = celery_mongo_db.celery_taskmeta
        task1_result, task2_result = [
            retry_on_condition(
                get_taskmeta_output, celery_taskmeta, task_metadata,
                condition=is_attribute_none, retries=20, interval=1,
            )
            for task_metadata in task_results
        ]

        # following errors are not necessarily linked directly to celery failing
        # however, if all other tests pass except this one, there's a big chance
        # it is caused by a celery concurrency/processes/threading issue with the pyramid registry
        potential_errors = [
            "AttributeError: 'NoneType' object",
            "if settings.get(setting, None) is None",
            "get_registry()",
            "get_settings()",
            "get_db()",
            "get_registry(app)",
            "get_settings(app)",
            "get_db(app)",
            "get_registry(celery_app)",
            "get_settings(celery_app)",
            "get_db(celery_app)",
            "get_registry(None)",
            "get_settings(None)",
            "get_db(None)",
        ]
        task1_found_errors = [err_msg for err_msg in potential_errors if err_msg in task1_result]
        task2_found_errors = [err_msg for err_msg in potential_errors if err_msg in task2_result]
        assert not task1_found_errors, "potential error detected with celery and pyramid registry utilities"
        assert not task2_found_errors, "potential error detected with celery and pyramid registry utilities"
