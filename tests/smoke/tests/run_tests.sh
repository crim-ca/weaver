#!/usr/bin/env bash

# WARNING:
#   can only use builtin unittest module to run tests within docker smoke-tests because built
#   images remove installers limiting the runtime addition of pytest and other test runners
python -m unittest discover -s /tests -p 'test_*.py' -v
