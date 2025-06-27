#!/usr/bin/env python
"""
Run operations specifically within the built Docker container to ensure Weaver runtime dependencies are available.
"""
import inspect
import subprocess
import tempfile


def test_weaver_app_legacy_egg_config_ini() -> None:
    """
    Ensures that the 'egg:weaver' module can be resolved at runtime (within Docker as smoke test).

    The new official 'egg:crim-weaver' module is employed to match the installed package name that should resolve
    automatically. This test ensures that the legacy 'egg:weaver' reference used in prior configurations remains
    functional to avoid breaking existing deployments that may still reference it.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix="weaver.ini") as tmp_ini:
        tmp_ini.writelines(inspect.cleandoc("""
            [app:main]
            use = egg:weaver

            mongodb.host = mongodb-does-not-exist
            mongodb.port = 27017
            mongodb.db_name = weaver
            mongodb.timeoutMS = 10

            [celery]
            broker_url = mongodb://mongodb-does-not-exist:27017/celery

            [server:main]
            use = egg:gunicorn#main
            bind = 0.0.0.0:44444
            workers = 1
            timeout = 1
        """))
        tmp_ini.flush()
        tmp_ini.seek(0)

        with subprocess.Popen(["pserve", tmp_ini.name], stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:
            out, err = proc.communicate()
            msg = f"{out.decode('utf-8').strip()}\n{err.decode('utf-8').strip()}"
        assert (
            "pymongo.errors.ServerSelectionTimeoutError" in msg
            and "distribution" not in msg
            and "PackageNotFoundError" not in msg
        ), (
            "Expected server selection timeout error to occur (purposely) when establishing the DB connection, "
            "indicating that prior 'egg:weaver' module resolution and import to instantiate the application "
            "succeeded at runtime by the pyramid application INI paste-deploy. "
            f"\nGot instead:\n\n{msg}\n"
        )
