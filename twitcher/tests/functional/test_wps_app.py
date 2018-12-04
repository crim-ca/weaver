"""
Based on tests from:

* https://github.com/geopython/pywps/tree/master/tests
* https://github.com/mmerickel/pyramid_services/tree/master/pyramid_services/tests
* http://webtest.pythonpaste.org/en/latest/
* http://docs.pylonsproject.org/projects/pyramid/en/latest/narr/testing.html
"""
# noinspection PyPackageRequirements
import mock
# noinspection PyPackageRequirements
import pytest
# noinspection PyPackageRequirements
import webtest
import unittest
import pyramid.testing
import pyramid_celery
from xml.etree import ElementTree
from twitcher.visibility import VISIBILITY_PUBLIC, VISIBILITY_PRIVATE
from twitcher.processes.wps_default import Hello
from twitcher.processes.wps_testing import WpsTestProcess
from twitcher.tests.functional.common import (
    setup_with_mongodb,
    setup_mongodb_processstore,
    setup_mongodb_tokenstore,
    setup_with_pywps,
    setup_celery,
)


@pytest.mark.functional
class WpsAppTest(unittest.TestCase):
    def setUp(self):
        self.wps_path = '/ows/wps'
        config = setup_with_mongodb()
        config.registry.settings['twitcher.url'] = ''
        config.registry.settings['twitcher.wps'] = True
        config.registry.settings['twitcher.wps_path'] = self.wps_path
        config = setup_with_pywps(config)
        config.include('twitcher.wps')
        config.include('twitcher.tweens')

        # override celery loader to specify configuration directly instead of ini file
        pyramid_celery.loaders.INILoader.read_configuration = mock.MagicMock(return_value=setup_celery(config))
        config.include('pyramid_celery')
        config.configure_celery('')     # value doesn't matter because overloaded
        self.process_store = setup_mongodb_processstore(config)
        self.token = setup_mongodb_tokenstore(config)
        self.app = webtest.TestApp(config.make_wsgi_app())

        self.process_public = WpsTestProcess(identifier='process_public')
        self.process_private = WpsTestProcess(identifier='process_private')
        self.process_store.save_process(self.process_public)
        self.process_store.save_process(self.process_private)
        self.process_store.set_visibility(self.process_public.identifier, VISIBILITY_PUBLIC)
        self.process_store.set_visibility(self.process_private.identifier, VISIBILITY_PRIVATE)

        # default process Hello needs visibility
        self.process_store.set_visibility(Hello.identifier, VISIBILITY_PUBLIC)

    def tearDown(self):
        pyramid.testing.tearDown()

    def make_url(self, params, token=None):
        return '{}?{}&access_token={}'.format(self.wps_path, params, token or self.token)

    @pytest.mark.online
    def test_getcaps(self):
        resp = self.app.get(self.make_url("service=wps&request=getcapabilities"))
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:Capabilities>')

    @pytest.mark.online
    def test_getcaps_filtered_processes_by_visibility(self):
        resp = self.app.get(self.make_url("service=wps&request=getcapabilities"))
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('<wps:ProcessOfferings>')
        root = ElementTree.fromstring(resp.text)
        process_offerings = list(filter(lambda e: 'ProcessOfferings' in e.tag, list(root)))
        assert len(process_offerings) == 1
        processes = [p for p in process_offerings[0]]
        identifiers = [pi.text for pi in [filter(lambda e: e.tag.endswith('Identifier'), p)[0] for p in processes]]
        assert self.process_private.identifier not in identifiers
        assert self.process_public.identifier in identifiers

    @pytest.mark.online
    def test_getcaps_with_invalid_token(self):
        resp = self.app.get(self.make_url("service=wps&request=getcapabilities", token='invalid'))
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('<wps:ProcessOfferings>')

    @pytest.mark.online
    def test_describeprocess(self):
        params = "service=wps&request=describeprocess&version=1.0.0&identifier={}".format(Hello.identifier)
        resp = self.app.get(self.make_url(params))
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:ProcessDescriptions>')

    @pytest.mark.online
    def test_describeprocess_with_invalid_token(self):
        params = "service=wps&request=describeprocess&version=1.0.0&identifier={}".format(Hello.identifier)
        url = self.make_url(params, token='invalid')
        resp = self.app.get(url)
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:ProcessDescriptions>')

    @pytest.mark.online
    def test_describeprocess_filtered_processes_by_visibility(self):
        param_template = "service=wps&request=describeprocess&version=1.0.0&identifier={}"

        url = self.make_url(param_template.format(self.process_public.identifier))
        resp = self.app.get(url)
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('</wps:ProcessDescriptions>')

        url = self.make_url(param_template.format(self.process_private.identifier))
        resp = self.app.get(url, expect_errors=True)
        assert resp.status_code == 400
        assert resp.content_type == 'text/xml'
        resp.mustcontain('<ows:ExceptionText>Unknown process')

    @pytest.mark.xfail(reason="Access token validation not implemented.")
    @unittest.expectedFailure
    @pytest.mark.online
    def test_execute_not_allowed(self):
        params = "service=wps&request=execute&version=1.0.0&identifier={}&datainputs=name=tux".format(Hello.identifier)
        url = self.make_url(params)
        resp = self.app.get(url)
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('<Exception exceptionCode="NoApplicableCode" locator="AccessForbidden">')

    @pytest.mark.online
    def test_execute_allowed(self):
        params = "service=wps&request=execute&version=1.0.0&identifier={}&datainputs=name=tux".format(Hello.identifier)
        url = self.make_url(params, token=self.token)
        resp = self.app.get(url)
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('<wps:ProcessSucceeded>PyWPS Process {} finished</wps:ProcessSucceeded>'.format(Hello.title))

    @pytest.mark.online
    def test_execute_with_visibility(self):
        params_template = "service=wps&request=execute&version=1.0.0&identifier={}&datainputs=test_input=test"
        url = self.make_url(params_template.format(self.process_public.identifier, ), token=self.token)
        resp = self.app.get(url)
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('<wps:ProcessSucceeded>PyWPS Process {} finished</wps:ProcessSucceeded>'
                         .format(self.process_public.title))

        url = self.make_url(params_template.format(self.process_private.identifier), token=self.token)
        resp = self.app.get(url, expect_errors=True)
        assert resp.status_code == 400
        assert resp.content_type == 'text/xml'
        resp.mustcontain('<ows:ExceptionText>Unknown process')
