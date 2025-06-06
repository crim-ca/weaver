#!/usr/bin/env bash

pip install pytest
pytest /tests -vvv --cache-dir /tmp
