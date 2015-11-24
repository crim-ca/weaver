from nose.tools import assert_equals, assert_raises

from twitcher import utils

def test_baseurl():
    assert_equals(utils.baseurl('http://localhost:8094/wps'), 'http://localhost:8094/wps')
    assert_equals(utils.baseurl('http://localhost:8094/wps?service=wps&request=getcapabilities'), 'http://localhost:8094/wps')
    assert_equals(utils.baseurl('https://localhost:8094/wps?service=wps&request=getcapabilities'), 'https://localhost:8094/wps')
    with assert_raises(ValueError) as e:
        utils.baseurl('ftp://localhost:8094/wps')


def test_path_elements():
    assert_equals(utils.path_elements('/ows/proxy/lovely_bird'), ['ows', 'proxy', 'lovely_bird'])
    assert_equals(utils.path_elements('/ows/proxy/lovely_bird/'), ['ows', 'proxy', 'lovely_bird'])
    assert_equals(utils.path_elements('/ows/proxy/lovely_bird/ '), ['ows', 'proxy', 'lovely_bird'])
