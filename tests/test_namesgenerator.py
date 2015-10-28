from nose.tools import assert_equals

from pywpsproxy.utils import namesgenerator

def test_get_random_name():
    name = namesgenerator.get_random_name()
    assert len(name) > 3
    assert '_' in name

def test_get_random_name_retry():
    name = namesgenerator.get_random_name(retry=True)
    assert len(name) > 3
    assert int(name[-1]) >= 0
