"""
Test WPS endpoint.
"""
import contextlib
import copy
from typing import TYPE_CHECKING

import pytest
import xmltodict
from parameterized import parameterized

from tests.functional.utils import ResourcesUtil, WpsConfigBase
from tests.utils import mocked_execute_celery
from weaver import xml_util
from weaver.execute import ExecuteControlOption
from weaver.formats import ContentType
from weaver.owsexceptions import OWSInvalidParameterValue
from weaver.processes.wps_default import HelloWPS
from weaver.processes.wps_testing import WpsTestProcess
from weaver.visibility import Visibility

if TYPE_CHECKING:
    from typing import List

    from weaver.typedefs import JSON


@pytest.mark.wps
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

    def test_describeprocess_invalid_id_bad_request_xml(self):
        bad_id = "$ohNoYouDont!"
        params = f"service=wps&request=describeprocess&version=1.0.0&identifier={bad_id}"
        resp = self.app.get(self.make_url(params), expect_errors=True)
        assert resp.status_code == 400
        assert resp.content_type in ContentType.ANY_XML
        resp.mustcontain("</ExceptionReport>")
        resp.mustcontain(f"[\"{bad_id}\"]")

    def test_describeprocess_invalid_id_bad_request_json(self):
        bad_id = "$ohNoYouDont!"
        params = f"service=wps&request=describeprocess&version=1.0.0&identifier={bad_id}"
        resp = self.app.get(self.make_url(params), expect_errors=True, headers={"Accept": ContentType.APP_JSON})
        assert resp.status_code == 400
        assert resp.content_type in ContentType.APP_JSON
        assert resp.json["code"] == OWSInvalidParameterValue.code
        assert resp.json["value"] == [bad_id]

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


@pytest.mark.wps
@pytest.mark.functional
class WpsAppTestWithProcessRevisions(WpsConfigBase, ResourcesUtil):
    wps_path = "/ows/wps"
    settings = {
        "weaver.url": "https://localhost",
        "weaver.wps": True,
        "weaver.wps_path": wps_path,
        "weaver.wps_metadata_identification_title": "Weaver WPS Test Server",
        "weaver.wps_metadata_provider_name": "WpsAppTest"
    }
    process_ids = None
    process_revisions = None

    @classmethod
    def setUpClass(cls):
        super(WpsAppTestWithProcessRevisions, cls).setUpClass()
        cls.process_ids = [
            cls.fully_qualified_test_name(cls, name=idx)
            for idx in [1, 2]
        ]
        cls.process_revisions = [
            cls.deploy_process_revisions(cls, proc_id)
            for proc_id in cls.process_ids
        ]

    def deploy_process_revisions(self, process_id):
        # type: (str) -> List[str]
        """
        Generates some revisions of a given process.
        """
        body = self.retrieve_payload("Echo", "deploy", local=True)
        versions = ["1.2.0"]
        body["processDescription"]["process"]["version"] = versions[0]
        self.deploy_process(body, process_id=process_id)
        data = {"title": "first revision", "version": "1.2.3"}
        resp = self.app.patch_json(f"/processes/{process_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 200
        versions.append(data["version"])
        data = {"title": "second revision", "version": "1.2.5"}
        resp = self.app.patch_json(f"/processes/{process_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 200
        versions.append(data["version"])
        data = {"title": "third revision", "version": "1.3.2", "jobControlOptions": [ExecuteControlOption.SYNC]}
        resp = self.app.patch_json(f"/processes/{process_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 200
        versions.append(data["version"])
        data = {"title": "fourth revision", "version": "1.3.4"}
        resp = self.app.patch_json(f"/processes/{process_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 200
        versions.append(data["version"])
        data = copy.deepcopy(body)  # type: JSON
        data_update = {"version": "2.0.0", "inputs": {"message": {"type": "string"}}}
        data["processDescription"]["process"].update(data_update)
        resp = self.app.put_json(f"/processes/{process_id}", params=data, headers=self.json_headers)
        assert resp.status_code == 201
        versions.append(data_update["version"])
        return versions

    @parameterized.expand([
        "", "1.2.3", "1.2.5", "1.3.2", "1.3.4", "2.0.0"
    ])
    def test_describe_process_single_revision(self, process_revision):
        headers = {"Accept": ContentType.APP_XML}
        proc_id = f"{self.process_ids[0]}:{process_revision}" if process_revision else self.process_ids[0]
        proc_ver = process_revision if process_revision else self.process_revisions[0][-1]
        params = {
            "service": "WPS",
            "request": "DescribeProcess",
            "version": "1.0.0",
            "identifier": proc_id,
        }
        resp = self.app.get(self.wps_path, params=params, headers=headers)
        assert resp.status_code == 200
        assert resp.content_type in ContentType.ANY_XML
        resp.mustcontain("</wps:ProcessDescriptions>")
        resp.mustcontain(f"ProcessDescription wps:processVersion=\"{proc_ver}\"")  # reported regardless of ID:rev
        resp.mustcontain(f"<ows:Identifier>{proc_id}</ows:Identifier>")  # ID as requested to match search criteria

    @parameterized.expand([
        # list of process ID index and revision to describe
        # they must be nested in tuples to be passed as single argument
        ([(0, "1.2.3"), (1, "1.2.5")], ),
        # ensure "same tag" is not mixed between distinct process ID
        ([(0, "1.3.2"), (1, "1.3.2"), (0, "1.3.4"), (1, "2.0.0")], ),
        # ensure optional tag returns both variants as pseudo-duplicates when the corresponding revision is also given
        # ("" == "2.0.0"), this is not the same as 'test_describe_process_multi_revision_duplicates' use case
        ([(0, "1.2.5"), (0, ""), (0, "2.0.0"), (0, ""), (1, "2.0.0")], ),
    ])
    def test_describe_process_multi_revision_filter(self, process_revisions):
        headers = {"Accept": ContentType.APP_XML}
        proc_ids = [
            f"{self.process_ids[idx]}:{rev}" if rev else self.process_ids[idx]
            for idx, rev in process_revisions
        ]
        proc_vers = [
            rev if rev else self.process_revisions[0][-1]
            for rev in process_revisions
        ]
        params = {
            "service": "WPS",
            "request": "DescribeProcess",
            "version": "1.0.0",
            "identifier": ",".join(proc_ids),
        }
        resp = self.app.get(self.wps_path, params=params, headers=headers)
        assert resp.status_code == 200
        assert resp.content_type in ContentType.ANY_XML
        resp.mustcontain("</wps:ProcessDescriptions>")
        for proc_id, proc_ver in zip(proc_ids, proc_vers):
            resp.mustcontain(f"ProcessDescription wps:processVersion=\"{proc_ver}\"")  # reported regardless of ID:rev
            resp.mustcontain(f"<ows:Identifier>{proc_id}</ows:Identifier>")  # ID as requested to match search criteria

        unrequested_versions = set(self.process_revisions[0]) - set(proc_vers)
        for proc_ver in unrequested_versions:
            assert f"ProcessDescription wps:processVersion=\"{proc_ver}\"" not in resp.text, "filter did not work"

        # number of identifiers must match the requested IDs/revisions that exist,
        # even if they represent the same process after optional-latest revision resolution
        # to ensure that PyWPS can resolve them against the specified query string ID values
        # (PyWPS does not have special 'revision' logic, it considers them distinct processes without relationships)
        assert resp.text.count("<ows:Identifier>") == len(process_revisions)

    def test_describe_process_multi_revision_duplicates(self):
        headers = {"Accept": ContentType.APP_XML}
        prov_rev = self.process_revisions[0][0]
        proc_id_rev = f"{self.process_ids[0]}:{prov_rev}"
        params = {
            "service": "WPS",
            "request": "DescribeProcess",
            "version": "1.0.0",
            # redundant IDs specified twice, which are not the latest (real duplicates)
            "identifier": f"{proc_id_rev},{proc_id_rev}",
        }
        resp = self.app.get(self.wps_path, params=params, headers=headers)
        assert resp.status_code == 200
        assert resp.content_type in ContentType.ANY_XML
        resp.mustcontain("</wps:ProcessDescriptions>")
        resp.mustcontain(f"ProcessDescription wps:processVersion=\"{prov_rev}\"")
        assert resp.text.count(f"<ows:Identifier>{proc_id_rev}</ows:Identifier>") == 1, (
            "Duplicate literal process 'ID:revision' should not result in duplicate entries in listing."
        )

    @parameterized.expand([
        # 1st revision is an older version that must be specified to invoke it specifically
        # 2 last versions are the same, but revision specified explicitly or not
        "1.2.3", "2.0.0", ""
    ])
    def test_execute_single_revision(self, process_revision):
        headers = {"Accept": ContentType.APP_XML}
        proc_id = f"{self.process_ids[0]}:{process_revision}" if process_revision else self.process_ids[0]
        params = {
            "service": "WPS",
            "request": "Execute",
            "version": "1.0.0",
            "identifier": proc_id,
            "dataInputs": "message=test",
        }
        with contextlib.ExitStack() as stack_exec:
            for mock_exec in mocked_execute_celery():
                stack_exec.enter_context(mock_exec)
            resp = self.app.get(self.wps_path, params=params, headers=headers)
        assert resp.status_code == 200
        assert resp.content_type in ContentType.ANY_XML
        resp.mustcontain("<wps:ExecuteResponse")
        resp.mustcontain("<wps:ProcessAccepted")
        resp.mustcontain(f"PyWPS Process {proc_id}")
