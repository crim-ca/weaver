"""
Based on tests from:

* https://github.com/geopython/pywps/tree/master/tests
* https://github.com/mmerickel/pyramid_services/tree/master/pyramid_services/tests
* http://webtest.pythonpaste.org/en/latest/
* http://docs.pylonsproject.org/projects/pyramid/en/latest/narr/testing.html
"""
# noinspection PyPackageRequirements
import pytest
# noinspection PyPackageRequirements
import webtest
import unittest
import pyramid.testing
import sys
import os
from xml.etree import ElementTree
from twitcher.visibility import VISIBILITY_PUBLIC, VISIBILITY_PRIVATE
from twitcher.processes.wps_default import Hello
from twitcher.processes.wps_testing import WpsTestProcess
from twitcher.tests.utils import get_default_config_ini_path
from twitcher.tests.functional.common import (
    setup_with_mongodb,
    setup_mongodb_processstore,
    setup_mongodb_tokenstore,
    setup_with_pywps,
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
        config.include('pyramid_celery')
        sys.path.append(os.path.expanduser('~/birdhouse/etc/celery'))   # allow finding celeryconfig
        config.configure_celery(get_default_config_ini_path())
        self.process = setup_mongodb_processstore(config)
        self.token = setup_mongodb_tokenstore(config)
        self.app = webtest.TestApp(config.make_wsgi_app())

        self.process_public = WpsTestProcess(identifier='process_public')
        self.process_private = WpsTestProcess(identifier='process_private')
        self.process.save_process(self.process_public)
        self.process.save_process(self.process_private)
        self.process.set_visibility(self.process_public.identifier, VISIBILITY_PUBLIC)
        self.process.set_visibility(self.process_private.identifier, VISIBILITY_PRIVATE)

        # default process Hello needs visibility
        self.process.set_visibility(Hello.identifier, VISIBILITY_PUBLIC)

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
        resp.mustcontain('</wps:Capabilities>')

    @pytest.mark.online
    def test_getcaps_with_invalid_token(self):
        resp = self.app.get(self.make_url("service=wps&request=getcapabilities", token='invalid'))
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('<wps:ProcessOfferings>')
        tree = ElementTree.parse(resp)
        root = tree.getroot()
        getcap_processes_ids = [process.get('ows:Identifier') for process in root.findall('wps:Process')]
        assert self.private_process.id not in getcap_processes_ids
        assert self.public_process.id in getcap_processes_ids

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
        url = self.make_url(params)
        url += "&access_token={}".format(self.token)
        resp = self.app.get(url)
        assert resp.status_code == 200
        assert resp.content_type == 'text/xml'
        resp.mustcontain('<wps:ProcessSucceeded>PyWPS Process {} finished</wps:ProcessSucceeded>'.format(Hello.title))
