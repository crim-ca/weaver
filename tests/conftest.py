#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging.config

from weaver.config import WEAVER_DEFAULT_INI_CONFIG, get_weaver_config_file


def pytest_configure(config):
    """
    Test configurations

    Log level in ``setup.cfg`` is purposely ``log_level = DEBUG`` to get `Weaver` and related debug messages from tests.
    However, this causes other less-critical packages to inherit this configuration globally.
    Load any user defined ``weaver.ini`` (or ``weaver.ini.example`` if misssing) logging overrides for tests.
    """
    config_path = get_weaver_config_file(None, WEAVER_DEFAULT_INI_CONFIG)
    logging.config.fileConfig(config_path)
