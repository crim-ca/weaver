#!/usr/bin/env bash

pip install pytest
pytest /tests -vvv -p no:cacheprovider
