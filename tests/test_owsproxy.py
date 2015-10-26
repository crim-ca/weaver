"""
based on `papyrus_ogcproxy <https://github.com/elemoine/papyrus_ogcproxy>`_

pyramid testing:

* http://docs.pylonsproject.org/projects/pyramid/en/latest/quick_tutorial/routing.html
"""

import unittest
import mock
from nose import SkipTest
from nose.plugins.attrib import attr

from pyramid import testing


## class IncludeMeTests(unittest.TestCase):
##     def setUp(self):
##         self.config = testing.setUp()

##     def tearDown(self):
##         testing.tearDown()

##     def test(self):
##         from pyramid.interfaces import IRoutesMapper
##         from pywpsproxy.owsproxy import includeme
##         views = []

##         def dummy_add_view(view, route_name=''):
##             views.append(view)
##         self.config.add_view = dummy_add_view
##         includeme(self.config)
##         self.assertEqual(len(views), 1)
##         mapper = self.config.registry.getUtility(IRoutesMapper)
##         routes = mapper.get_routes()
##         self.assertEqual(len(routes), 1)
##         self.assertEqual(routes[0].name, 'owsproxy')
##         self.assertEqual(routes[0].path, '/owsproxy')


class MainTests(unittest.TestCase):
    def test(self):
        from pywpsproxy import main
        app = main({}, a='a')
        from pyramid.router import Router
        self.assertTrue(isinstance(app, Router))


class OWSProxyTests(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()
        from pywpsproxy.owsproxy import views
        views.allowed_hosts = ()

    def test_badrequest_url(self):
        from pywpsproxy.owsproxy.views import OWSProxy
        from pyramid.testing import DummyRequest
        request = DummyRequest(scheme='http')
        inst = OWSProxy(request)
        response = inst.owsproxy()
        from pyramid.httpexceptions import HTTPBadRequest
        self.assertTrue(isinstance(response, HTTPBadRequest))

    def test_badrequest_netloc(self):
        from pywpsproxy.owsproxy.views import OWSProxy
        from pyramid.testing import DummyRequest
        request = DummyRequest(scheme='http',
                               params={'url': 'http://'})
        inst = OWSProxy(request)
        response = inst.owsproxy()
        from pyramid.httpexceptions import HTTPBadRequest
        self.assertTrue(isinstance(response, HTTPBadRequest))

    def test_badgateway_url(self):
        raise SkipTest
        from pywpsproxy.owsproxy.views import OWSProxy
        from pyramid.testing import DummyRequest
        request = DummyRequest(scheme='http',
                               params={'url': 'http://__foo__.__toto__'})
        inst = OWSProxy(request)
        response = inst.owsproxy()
        from pyramid.httpexceptions import HTTPBadGateway
        self.assertTrue(isinstance(response, HTTPBadGateway))

    def test_forbidden_content_type(self):
        raise SkipTest
        from pywpsproxy.owsproxy.views import OWSProxy
        from pyramid.testing import DummyRequest
        request = DummyRequest(scheme='http',
                               params={'url': 'http://www.google.com'})
        response = OWSProxy(request)
        from pyramid.httpexceptions import HTTPForbidden
        self.assertTrue(isinstance(response, HTTPForbidden))

    def test_forbidden_content_type_with_post(self):
        raise SkipTest
        from pywpsproxy.owsproxy.views import OWSProxy
        from pyramid.testing import DummyRequest
        request = DummyRequest(scheme='http',
                               params={'url': 'http://www.google.com'},
                               post='foo')
        response = OWSProxy(request)
        from pyramid.httpexceptions import HTTPForbidden
        self.assertTrue(isinstance(response, HTTPForbidden))

    @mock.patch('pywpsproxy.owsproxy.views.Http')
    def test_notacceptable_no_content_type(self, MockClass):
        raise SkipTest
        instance = MockClass.return_value
        instance.request.return_value = ({}, 'content')
        from pywpsproxy.owsproxy.views import OWSProxy
        from pyramid.testing import DummyRequest
        request = DummyRequest(scheme='http',
                               params={'url': 'http://www.google.com'})
        response = OWSProxy(request)
        from pyramid.httpexceptions import HTTPNotAcceptable
        self.assertTrue(isinstance(response, HTTPNotAcceptable))

    def test_allowed_host(self):
        raise SkipTest
        from pywpsproxy.owsproxy import views
        from pywpsproxy.owsproxy.views import OWSProxy
        from pyramid.testing import DummyRequest
        views.allowed_hosts = ('www.google.com')
        request = DummyRequest(scheme='http',
                               params={'url': 'http://www.google.com'})
        response = OWSProxy(request)
        from pyramid.response import Response
        self.assertTrue(isinstance(response, Response))
        self.assertEqual(response.status_int, 200)
        self.assertEqual(response.content_type, 'text/html')

    def test_allowed_content_type_wps(self):
        raise SkipTest
        from pywpsproxy.owsproxy.views import OWSProxy
        from pyramid.testing import DummyRequest
        request = DummyRequest(scheme='http', params={'VERSION': '1.0.0', 'SERVICE': 'WMS', 'REQUEST': 'GetCapabilities'})
        request.matchdict['ows_service'] = 'emu'
        inst = OWSProxy(request)
        response = inst.owsproxy()
        from pyramid.response import Response
        self.assertTrue(isinstance(response, Response))
        self.assertEqual(response.status_int, 200)
        self.assertEqual(response.content_type, 'text/xml')
