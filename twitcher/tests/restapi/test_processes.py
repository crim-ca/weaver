# noinspection PyPackageRequirements
import pytest
# noinspection PyPackageRequirements
import webtest
import unittest
import pyramid.testing
import six
from twitcher.tests.functional.common import setup_with_mongodb, setup_mongodb_processstore, setup_mongodb_jobstore
from twitcher.processes.wps_testing import WpsTestProcess
from twitcher.visibility import VISIBILITY_PUBLIC, VISIBILITY_PRIVATE


class WpsRestApiProcessesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = setup_with_mongodb()
        cls.config.include('twitcher.wps')
        cls.config.include('twitcher.wps_restapi')
        cls.config.include('twitcher.tweens')
        cls.config.scan()
        cls.json_app = 'application/json'
        cls.json_headers = {'Accept': cls.json_app, 'Content-Type':cls.json_app}
        cls.app = webtest.TestApp(cls.config.make_wsgi_app())

    @classmethod
    def tearDownClass(cls):
        pyramid.testing.tearDown()

    def setUp(self):
        # rebuild clean db on each test
        self.process_store = setup_mongodb_processstore(self.config)
        self.job_store = setup_mongodb_jobstore(self.config)

        self.process_public = WpsTestProcess(identifier='process_public')
        self.process_private = WpsTestProcess(identifier='process_private')
        self.process_store.save_process(self.process_public)
        self.process_store.save_process(self.process_private)
        self.process_store.set_visibility(self.process_public.identifier, VISIBILITY_PUBLIC)
        self.process_store.set_visibility(self.process_private.identifier, VISIBILITY_PRIVATE)

    def test_get_processes(self):
        uri = '/processes'
        resp = self.app.get(uri, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == self.json_app
        assert 'processes' in resp.json and isinstance(resp.json['processes'], list) and len(resp.json['processes']) > 0
        for process in resp.json['processes']:
            assert 'id' in process and isinstance(process['id'], six.string_types)
            assert 'title' in process and isinstance(process['title'], six.string_types)
            assert 'version' in process and isinstance(process['version'], six.string_types)
            assert 'keywords' in process and isinstance(process['keywords'], list)
            assert 'metadata' in process and isinstance(process['metadata'], list)

        processes_id = [p['id'] for p in resp.json['processes']]
        assert self.process_public.identifier in processes_id
        assert self.process_private.identifier not in processes_id

    def test_describe_process_visibility_public(self):
        uri = '/processes/{}'.format(self.process_public.identifier)
        resp = self.app.get(uri, headers=self.json_headers)
        assert resp.status_code == 200
        assert resp.content_type == self.json_app

    def test_describe_process_visibility_private(self):
        uri = '/processes/{}'.format(self.process_private.identifier)
        resp = self.app.get(uri, headers=self.json_headers, expect_errors=True)
        assert resp.status_code == 401
        assert resp.content_type == self.json_app

    def test_create_process(self):
        pass

    def test_delete_process(self):
        pass

    def test_execute_process(self):
        pass

    def test_get_process_visibility(self):
        pass

    def test_set_process_visibility(self):
        pass
