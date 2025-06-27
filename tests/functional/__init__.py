import os
import pytest

APP_PKG_ROOT = os.path.join(os.path.dirname(__file__), "application-packages")
TEST_DATA_ROOT = os.path.join(os.path.dirname(__file__), "test-data")

pytestmark = pytest.mark.functional
