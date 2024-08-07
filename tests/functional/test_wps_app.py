"""
Based on tests from:

* https://github.com/geopython/pywps/tree/master/tests
* https://github.com/mmerickel/pyramid_services/tree/master/pyramid_services/tests
* http://webtest.pythonpaste.org/en/latest/
* http://docs.pylonsproject.org/projects/pyramid/en/latest/narr/testing.html
"""
import contextlib

import pytest
import xmltodict

from tests.functional.utils import WpsConfigBase
from tests.utils import mocked_execute_celery
from weaver import xml_util
from weaver.formats import ContentType
from weaver.processes.wps_default import HelloWPS
from weaver.processes.wps_testing import WpsTestProcess
from weaver.visibility import Visibility


@pytest.mark.functional
class WpsAppTest(WpsConfigBase):
    wps_path = "/ows/wps"
    settings = {
        "weaver.url": "https://localhost",
        "weaver.wps": True,
        "weaver.wps_path": wps_path,
        "weaver.wps_metadata_identification_title": "Weaver WPS Test Server",
        "weaver.wps_metadata_provider_name": "WpsAppTest"
    }
    process_public = None   # type: WpsTestProcess
    process_private = None  # type: WpsTestProcess

    @classmethod
    def setUpClass(cls):
        super(WpsAppTest, cls).setUpClass()

        # add processes by database Process type
        cls.process_public = WpsTestProcess(identifier="process_public")
        cls.process_private = WpsTestProcess(identifier="process_private")
        cls.process_store.save_process(cls.process_public)
        cls.process_store.save_process(cls.process_private)
        cls.process_store.set_visibility(cls.process_public.identifier, Visibility.PUBLIC)
        cls.process_store.set_visibility(cls.process_private.identifier, Visibility.PRIVATE)

        # add processes by pywps Process type
        cls.process_store.save_process(HelloWPS())
        cls.process_store.set_visibility(HelloWPS.identifier, Visibility.PUBLIC)

    def make_url(self, params):
        return f"{self.wps_path}?{params}"

    def test_getcaps(self):
        resp = self.app.get(self.make_url("service=wps&request=getcapabilities"))
        assert resp.status_code == 200
        assert resp.content_type in ContentType.ANY_XML
        resp.mustcontain("</wps:Capabilities>")

    def test_getcaps_metadata(self):
        resp = self.app.get(self.make_url("service=wps&request=getcapabilities"))
        assert resp.status_code == 200
        assert resp.content_type in ContentType.ANY_XML
        xml_dict = xmltodict.parse(resp.text)
        assert xml_dict["wps:Capabilities"]["ows:ServiceIdentification"]["ows:Title"] == "Weaver WPS Test Server"
        assert xml_dict["wps:Capabilities"]["ows:ServiceProvider"]["ows:ProviderName"] == WpsAppTest.__name__

    def test_getcaps_filtered_processes_by_visibility(self):
        resp = self.app.get(self.make_url("service=wps&request=getcapabilities"))
        assert resp.status_code == 200
        assert resp.content_type in ContentType.ANY_XML
        resp.mustcontain("<wps:ProcessOfferings>")
        root = xml_util.fromstring(resp.text)  # test response has no 'content'
        process_offerings = list(filter(lambda e: "ProcessOfferings" in e.tag, root.iter(xml_util.Element)))
        assert len(process_offerings) == 1
        processes = [p for p in process_offerings[0]]
        ids = [pi.text for pi in [list(filter(lambda e: e.tag.endswith("Identifier"), p))[0] for p in processes]]
        assert self.process_private.identifier not in ids
        assert self.process_public.identifier in ids

    def test_describeprocess(self):
        template = "service=wps&request=describeprocess&version=1.0.0&identifier={}"
        params = template.format(HelloWPS.identifier)
        resp = self.app.get(self.make_url(params))
        assert resp.status_code == 200
        assert resp.content_type in ContentType.ANY_XML
        resp.mustcontain("</wps:ProcessDescriptions>")

    def test_describeprocess_json_format_query(self):
        template = "service=wps&request=describeprocess&version=1.0.0&identifier={}&f=json"
        params = template.format(HelloWPS.identifier)
        resp = self.app.get(self.make_url(params))
        assert 300 <= resp.status_code < 400, "redirect response to REST-JSON formatted endpoint expected"
        resp = resp.follow()
        assert resp.status_code == 200
        assert resp.content_type in ContentType.APP_JSON
        assert resp.json["id"] == HelloWPS.identifier

    def test_describeprocess_xml_format_from_restapi_url(self):
        url = f"/processes/{HelloWPS.identifier}"
        resp = self.app.get(url, headers={"Accept": ContentType.APP_XML})
        assert resp.status_code == 200
        assert resp.content_type in ContentType.ANY_XML
        resp.mustcontain("</wps:ProcessDescriptions>")

    def test_describeprocess_filtered_processes_by_visibility(self):
        param_template = "service=wps&request=describeprocess&version=1.0.0&identifier={}"

        url = self.make_url(param_template.format(self.process_public.identifier))
        resp = self.app.get(url)
        assert resp.status_code == 200
        assert resp.content_type in ContentType.ANY_XML
        resp.mustcontain("</wps:ProcessDescriptions>")

        url = self.make_url(param_template.format(self.process_private.identifier))
        resp = self.app.get(url, expect_errors=True)
        assert resp.status_code == 400
        assert resp.content_type in ContentType.ANY_XML
        resp.mustcontain("<ows:ExceptionText>Unknown process")

    def test_describeprocess_no_format_default_api_client(self):
        template = "service=wps&request=describeprocess&version=1.0.0&identifier={}"
        params = template.format(HelloWPS.identifier)
        resp = self.app.get(self.make_url(params), headers={"User-Agent": "Robot"})
        assert resp.status_code == 200
        assert resp.content_type in ContentType.ANY_XML
        resp.mustcontain("</wps:ProcessDescriptions>")

    def test_describeprocess_no_format_default_web_browser(self):
        template = "service=wps&request=describeprocess&version=1.0.0&identifier={}"
        params = template.format(HelloWPS.identifier)
        resp = self.app.get(self.make_url(params), headers={"User-Agent": "Mozilla/Test"})
        assert resp.status_code == 200
        assert resp.content_type in ContentType.ANY_XML
        resp.mustcontain("</wps:ProcessDescriptions>")

    def test_execute_allowed_demo(self):
        template = "service=wps&request=execute&version=1.0.0&identifier={}&datainputs=name=tux"
        params = template.format(HelloWPS.identifier)
        url = self.make_url(params)
        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            resp = self.app.get(url)
        assert resp.status_code == 200  # FIXME: replace by 202 Accepted (?) https://github.com/crim-ca/weaver/issues/14
        assert resp.content_type in ContentType.ANY_XML
        resp.mustcontain("<wps:ExecuteResponse")
        resp.mustcontain("<wps:ProcessAccepted")
        resp.mustcontain(f"PyWPS Process {HelloWPS.identifier}")

    def test_execute_allowed_empty_string(self):
        template = "service=wps&request=execute&version=1.0.0&identifier={}&datainputs=name="
        params = template.format(HelloWPS.identifier)
        url = self.make_url(params)
        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            resp = self.app.get(url)
        assert resp.status_code == 200  # FIXME: replace by 202 Accepted (?) https://github.com/crim-ca/weaver/issues/14
        assert resp.content_type in ContentType.ANY_XML
        resp.mustcontain("<wps:ExecuteResponse")
        resp.mustcontain("<wps:ProcessAccepted")
        resp.mustcontain(f"PyWPS Process {HelloWPS.identifier}")
        loc = resp.xml.get("statusLocation")
        job_id = loc.rsplit("/", 1)[-1].split(".", 1)[0]
        job = self.job_store.fetch_by_id(job_id)
        assert job.inputs[0]["data"] == ""

    def test_execute_deployed_with_visibility_allowed(self):
        headers = {"Accept": ContentType.APP_XML}
        params_template = "service=wps&request=execute&version=1.0.0&identifier={}&datainputs=test_input=test"
        url = self.make_url(params_template.format(self.process_public.identifier))
        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            resp = self.app.get(url, headers=headers)
        assert resp.status_code == 200  # FIXME: replace by 202 Accepted (?) https://github.com/crim-ca/weaver/issues/14
        assert resp.content_type in ContentType.ANY_XML
        resp.mustcontain("<wps:ExecuteResponse")
        resp.mustcontain("<wps:ProcessAccepted")
        resp.mustcontain(f"PyWPS Process {self.process_public.identifier}")

    def test_execute_deployed_with_visibility_denied(self):
        headers = {"Accept": ContentType.APP_XML}
        params_template = "service=wps&request=execute&version=1.0.0&identifier={}&datainputs=test_input=test"
        url = self.make_url(params_template.format(self.process_private.identifier))
        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            resp = self.app.get(url, headers=headers, expect_errors=True)
        assert resp.status_code == 403
        assert resp.content_type in ContentType.ANY_XML, f"Error Response: {resp.text}"
        resp.mustcontain("<Exception exceptionCode=\"AccessForbidden\" locator=\"service\">")
        err_desc = f"Process with ID '{self.process_private.identifier}' is not accessible."
        resp.mustcontain(f"<ExceptionText>{err_desc}</ExceptionText>")
