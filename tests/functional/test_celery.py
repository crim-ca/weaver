"""
Tests to validate that :mod:`celery` execution behaves as intended.
"""
import contextlib
import inspect
import json
import os
import subprocess
import sys
import tempfile
from typing import TYPE_CHECKING

import pytest

from tests.utils import get_settings_from_testapp, get_test_weaver_app, setup_config_with_mongodb
from weaver.config import WeaverConfiguration
from weaver.database import get_db
from weaver.database.mongodb import get_mongodb_connection
from weaver.utils import retry_on_condition
from weaver.wps.utils import get_wps_url

if TYPE_CHECKING:
    from pymongo.collection import Collection


def is_attribute_none(exception):
    # type: (Exception) -> bool
    return isinstance(exception, AttributeError) and any(err in str(exception) for err in ["None", "NoneType"])


def get_taskmeta_output(taskmeta_collection, output):
    # type: (Collection, str) -> str
    taskmeta = taskmeta_collection.find_one({"_id": output.strip()})
    return taskmeta.get("traceback", "") + taskmeta.get("result", "")


@pytest.mark.flaky(reruns=3, reruns_delay=1)
def test_celery_registry_resolution():
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
        celery_mongo_broker = f"""mongodb://{settings["mongodb.host"]}:{settings["mongodb.port"]}/celery-test"""
        cfg_ini = stack.enter_context(tempfile.NamedTemporaryFile(suffix=".ini", mode="w", encoding="utf-8"))
        cfg_ini.write(
            inspect.cleandoc(f"""
            [app:main]
            use = egg:weaver
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
                "--detach",
                # following will cause an error on any subsequent task
                # if registry is not properly retrieved across processes/threads
                "--concurrency", "1",
                "--max-tasks-per-child", "1",
            ],
            universal_newlines=True,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PATH": f"{python_dir}:{debug_path}"},
        ))  # type: subprocess.Popen
        celery_stdout, celery_stderr = celery_process.communicate()
        celery_output = celery_stdout + celery_stderr
        assert "Traceback" not in celery_output, "Unhandled error at Weaver/Celery startup. Cannot resume test."
        assert all([
            msg in celery_output
            for msg in
            [
                "Initiating weaver application",
                "Celery runner detected.",
            ]
        ])

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
            env={"PATH": f"{python_dir}:{debug_path}"},
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
            env={"PATH": f"{python_dir}:{debug_path}"},
        ))  # type: subprocess.Popen

        task1_output, _ = retry_on_condition(
            lambda: celery_task_cmd1.communicate(),
            condition=is_attribute_none, retries=5, interval=1,
        )
        task2_output, _ = retry_on_condition(
            lambda: celery_task_cmd2.communicate(),
            condition=is_attribute_none, retries=5, interval=1,
        )

        celery_mongo_db = get_mongodb_connection({
            "mongodb.host": settings["mongodb.host"],
            "mongodb.port": settings["mongodb.port"],
            "mongodb.db_name": "celery-test",
        })
        celery_taskmeta = celery_mongo_db.celery_taskmeta
        task1_result = retry_on_condition(
            get_taskmeta_output, celery_taskmeta, task1_output,
            condition=is_attribute_none, retries=5, interval=1,
        )
        task2_result = retry_on_condition(
            get_taskmeta_output, celery_taskmeta, task2_output,
            condition=is_attribute_none, retries=5, interval=1,
        )

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
