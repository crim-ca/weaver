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
##         from twitcher.owsproxy import includeme
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
        raise SkipTest
        from twitcher import main
        # TODO: fix mongodb init
        app = main({}, **{'twitcher.secret': 'testsecret',
                          'mongodb.host': 'localhost', 'mongodb.port': '27027', 'mongodb.db_name': 'testdb'})
        from pyramid.router import Router
        self.assertTrue(isinstance(app, Router))


class OWSProxyTests(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()
        from twitcher import owsproxy
        owsproxy.allowed_hosts = ()

    def test_badrequest_url(self):
        from twitcher.owsproxy import OWSProxy
        from pyramid.testing import DummyRequest
        request = DummyRequest(scheme='http')
        inst = OWSProxy(request)
        response = inst.owsproxy()
        from pyramid.httpexceptions import HTTPBadRequest
        self.assertTrue(isinstance(response, HTTPBadRequest))

    def test_badrequest_netloc(self):
        from twitcher.owsproxy import OWSProxy
        from pyramid.testing import DummyRequest
        request = DummyRequest(scheme='http',
                               params={'url': 'http://'})
        inst = OWSProxy(request)
        response = inst.owsproxy()
        from pyramid.httpexceptions import HTTPBadRequest
        self.assertTrue(isinstance(response, HTTPBadRequest))

   

   
   
