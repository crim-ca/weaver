# code taken from https://github.com/elemoine/papyrus_ogcproxy

import unittest
import mock
from nose import SkipTest
from nose.plugins.attrib import attr

from pyramid import testing


class IncludeMeTests(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()

    def test(self):
        from pyramid.interfaces import IRoutesMapper
        from pywpsproxy.ogcproxy import includeme
        views = []

        def dummy_add_view(view, route_name=''):
            views.append(view)
        self.config.add_view = dummy_add_view
        includeme(self.config)
        self.assertEqual(len(views), 1)
        mapper = self.config.registry.getUtility(IRoutesMapper)
        routes = mapper.get_routes()
        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0].name, 'ogcproxy')
        self.assertEqual(routes[0].path, '/ogcproxy')


class MainTests(unittest.TestCase):
    def test(self):
        from pywpsproxy import main
        app = main({}, a='a')
        from pyramid.router import Router
        self.assertTrue(isinstance(app, Router))


class OgcProxy(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()
        from pywpsproxy.ogcproxy import views
        views.allowed_hosts = ()

    def test_badrequest_url(self):
        from pywpsproxy.ogcproxy.views import ogcproxy
        from pyramid.testing import DummyRequest
        request = DummyRequest(scheme='http')
        response = ogcproxy(request)
        from pyramid.httpexceptions import HTTPBadRequest
        self.assertTrue(isinstance(response, HTTPBadRequest))

    def test_badrequest_netloc(self):
        from pywpsproxy.ogcproxy.views import ogcproxy
        from pyramid.testing import DummyRequest
        request = DummyRequest(scheme='http',
                               params={'url': 'http://'})
        response = ogcproxy(request)
        from pyramid.httpexceptions import HTTPBadRequest
        self.assertTrue(isinstance(response, HTTPBadRequest))

    def test_badgateway_url(self):
        from pywpsproxy.ogcproxy.views import ogcproxy
        from pyramid.testing import DummyRequest
        request = DummyRequest(scheme='http',
                               params={'url': 'http://__foo__.__toto__'})
        response = ogcproxy(request)
        from pyramid.httpexceptions import HTTPBadGateway
        self.assertTrue(isinstance(response, HTTPBadGateway))

    def test_forbidden_content_type(self):
        from pywpsproxy.ogcproxy.views import ogcproxy
        from pyramid.testing import DummyRequest
        request = DummyRequest(scheme='http',
                               params={'url': 'http://www.google.com'})
        response = ogcproxy(request)
        from pyramid.httpexceptions import HTTPForbidden
        self.assertTrue(isinstance(response, HTTPForbidden))

    def test_forbidden_content_type_with_post(self):
        from pywpsproxy.ogcproxy.views import ogcproxy
        from pyramid.testing import DummyRequest
        request = DummyRequest(scheme='http',
                               params={'url': 'http://www.google.com'},
                               post='foo')
        response = ogcproxy(request)
        from pyramid.httpexceptions import HTTPForbidden
        self.assertTrue(isinstance(response, HTTPForbidden))

    @mock.patch('pywpsproxy.ogcproxy.views.Http')
    def test_notacceptable_no_content_type(self, MockClass):
        instance = MockClass.return_value
        instance.request.return_value = ({}, 'content')
        from pywpsproxy.ogcproxy.views import ogcproxy
        from pyramid.testing import DummyRequest
        request = DummyRequest(scheme='http',
                               params={'url': 'http://www.google.com'})
        response = ogcproxy(request)
        from pyramid.httpexceptions import HTTPNotAcceptable
        self.assertTrue(isinstance(response, HTTPNotAcceptable))

    def test_allowed_host(self):
        from pywpsproxy.ogcproxy import views
        from pywpsproxy.ogcproxy.views import ogcproxy
        from pyramid.testing import DummyRequest
        views.allowed_hosts = ('www.google.com')
        request = DummyRequest(scheme='http',
                               params={'url': 'http://www.google.com'})
        response = ogcproxy(request)
        from pyramid.response import Response
        self.assertTrue(isinstance(response, Response))
        self.assertEqual(response.status_int, 200)
        self.assertEqual(response.content_type, 'text/html')

    def test_allowed_content_type(self):
        raise SkipTest
        from pywpsproxy.ogcproxy.views import ogcproxy
        from pyramid.testing import DummyRequest
        url = 'http://wms.jpl.nasa.gov/wms.cgi?' \
                  'SERVICE=WMS&REQUEST=GetCapabilities'
        request = DummyRequest(scheme='http', params={'url': url})
        response = ogcproxy(request)
        from pyramid.response import Response
        self.assertTrue(isinstance(response, Response))
        self.assertEqual(response.status_int, 200)
        self.assertEqual(response.content_type, 'application/vnd.ogc.wms_xml')
