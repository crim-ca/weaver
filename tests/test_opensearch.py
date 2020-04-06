import contextlib
import json
import os
import unittest
from collections import deque
from copy import deepcopy
from pprint import pformat
from urllib.parse import parse_qsl, urlparse

import mock
import pytest
from pyramid import testing
from pyramid.testing import DummyRequest
from pywps.inout.inputs import LiteralInput

from tests.utils import setup_mongodb_processstore
from weaver.datatype import Process
from weaver.processes import opensearch
from weaver.processes.constants import OPENSEARCH_AOI, OPENSEARCH_END_DATE, OPENSEARCH_START_DATE
from weaver.processes.opensearch import _make_specific_identifier  # noqa: W0212
from weaver.utils import get_any_id
from weaver.wps_restapi.processes import processes

OSDD_URL = "http://geo.spacebel.be/opensearch/description.xml"

COLLECTION_IDS = {
    "sentinel2": "EOP:IPT:Sentinel2",
    "probav": "EOP:VITO:PROBAV_P_V001",
    "deimos": "DE2_PS3_L1C",
}


def assert_json_equals(json1, json2):
    def ordered_json(obj):
        if isinstance(obj, dict):
            return sorted((str(k), ordered_json(v)) for k, v in obj.items())
        elif isinstance(obj, list):
            return sorted(ordered_json(x) for x in obj)
        else:
            return str(obj)

    json1_lines = pformat(ordered_json(json1)).split("\n")
    json2_lines = pformat(ordered_json(json2)).split("\n")
    for line1, line2 in zip(json1_lines, json2_lines):
        assert line1 == line2


def get_test_file(*args):
    return os.path.join(os.path.dirname(__file__), *args)


def load_json_test_file(filename):
    return json.load(open(get_test_file("json_examples", filename)))


def make_request(**kw):
    request = DummyRequest(**kw)
    if request.registry.settings is None:
        request.registry.settings = {}
    request.registry.settings["weaver.url"] = "localhost"
    request.registry.settings["weaver.wps_path"] = "/ows/wps"
    return request


class WpsHandleEOITestCase(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()


def get_dummy_payload():
    return {
        "processDescription": {
            "process": {
                "identifier": "workflow_stacker_sfs_id",
                "title": "Application StackCreation followed by SFS dynamically added by POST /processes",
                "owsContext": {
                    "offering": {
                        "code": "http://www.opengis.net/eoc/applicationContext/cwl",
                        "content": {
                            "href": "http://some.host/applications/cwl/multisensor_ndvi.cwl"
                        },
                    }
                },
            }
        }
    }


def get_opensearch_payload():
    return load_json_test_file("opensearch_deploy.json")


def get_opensearch_process():
    return Process(load_json_test_file("opensearch_process.json"))


def test_transform_execute_parameters_wps():
    def make_input(id_, value):
        input_ = LiteralInput(id_, "", data_type="string")
        input_.data = value
        return input_

    def make_deque(id_, value):
        input_ = make_input(id_, value)
        return id_, deque([input_])

    inputs = dict(
        [
            make_deque(OPENSEARCH_START_DATE, "2018-01-30T00:00:00.000Z"),
            make_deque(OPENSEARCH_END_DATE, "2018-01-31T23:59:59.999Z"),
            make_deque(OPENSEARCH_AOI, "100.4,15.3,104.6,19.3"),
            make_deque("files", COLLECTION_IDS["sentinel2"]),
            make_deque("output_file_type", "GEOTIFF"),
            make_deque("output_name", "stack_result.tif"),
        ]
    )

    mocked_query = ["file:///something.SAFE"]
    files_inputs = [make_input("files", "opensearch" + m) for m in mocked_query]

    expected = dict(
        [
            make_deque("output_file_type", "GEOTIFF"),
            make_deque("output_name", "stack_result.tif"),
            ("files", deque(files_inputs)),
        ]
    )

    with mock.patch.object(opensearch.OpenSearchQuery, "query_datasets", return_value=mocked_query):
        eo_image_source_info = make_eo_image_source_info("files", COLLECTION_IDS["sentinel2"])
        mime_types = {"files": eo_image_source_info["files"]["mime_types"]}
        transformed = opensearch.query_eo_images_from_wps_inputs(inputs, eo_image_source_info, mime_types)

    def compare(items):
        return sorted([(k, [v.data for v in values]) for k, values in items.items()])

    assert compare(transformed) == compare(expected)


@pytest.mark.skip(reason="The user-provided bbox is now a comma delimited string, not a WKT.")
def test_load_wkt():
    data = [
        ("POLYGON ((100 15, 104 15, 104 19, 100 19, 100 15))", "100.0,15.0,104.0,19.0"),
        (
            "LINESTRING (100 15, 104 15, 104 19, 100 19, 100 15)",
            "100.0,15.0,104.0,19.0",
        ),
        ("LINESTRING (100 15, 104 19)", "100.0,15.0,104.0,19.0"),
        ("MULTIPOINT ((10 10), (40 30), (20 20), (30 10))", "10.0,10.0,40.0,30.0"),
        ("POINT (30 10)", "30.0,10.0,30.0,10.0"),
    ]
    for wkt, expected in data:
        assert opensearch.load_wkt(wkt) == expected


def test_deploy_opensearch():
    store = setup_mongodb_processstore()

    class MockDB(object):
        def __init__(self, *args):
            pass

        def get_store(self, *args):  # noqa: E811
            return store

    def _get_mocked(req):
        return req.registry.settings

    # mock db functions called by add_local_process
    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch("weaver.wps_restapi.processes.processes.get_db", side_effect=MockDB))
        stack.enter_context(mock.patch("weaver.wps_restapi.processes.processes.get_settings", side_effect=_get_mocked))
        stack.enter_context(mock.patch("weaver.processes.utils.get_db", side_effect=MockDB))
        stack.enter_context(mock.patch("weaver.processes.utils.get_settings", side_effect=_get_mocked))
        # given
        opensearch_payload = get_opensearch_payload()
        initial_payload = deepcopy(opensearch_payload)
        request = make_request(json=opensearch_payload, method="POST")
        process_id = get_any_id(opensearch_payload["processDescription"]["process"])

        # when
        response = processes.add_local_process(request)

        # then
        assert response.code == 201
        assert response.json["deploymentDone"]
        process = store.fetch_by_id(process_id)
        assert process
        assert process.package
        assert process.payload
        assert_json_equals(process.payload, initial_payload)


def test_handle_eoi_unique_aoi_unique_toi():  # noqa
    inputs = load_json_test_file("eoimage_inputs_example.json")
    expected = load_json_test_file("eoimage_unique_aoi_unique_toi.json")
    output = opensearch.EOImageDescribeProcessHandler(
        inputs
    ).to_opensearch(unique_aoi=True, unique_toi=True)
    assert_json_equals(output, expected)


def test_handle_eoi_unique_aoi_non_unique_toi():
    inputs = load_json_test_file("eoimage_inputs_example.json")
    expected = load_json_test_file("eoimage_unique_aoi_non_unique_toi.json")
    output = opensearch.EOImageDescribeProcessHandler(
        inputs
    ).to_opensearch(unique_aoi=True, unique_toi=False)
    assert_json_equals(output, expected)


def test_handle_eoi_non_unique_aoi_unique_toi():
    inputs = load_json_test_file("eoimage_inputs_example.json")
    expected = load_json_test_file("eoimage_non_unique_aoi_unique_toi.json")
    output = opensearch.EOImageDescribeProcessHandler(
        inputs
    ).to_opensearch(unique_aoi=False, unique_toi=True)
    assert_json_equals(output, expected)


def test_get_additional_parameters():
    data = {
        "additionalParameters": [
            {
                "role": "http://www.opengis.net/eoc/applicationContext",
                "parameters": [
                    {"name": "UniqueAOI", "values": ["true"]},
                    {"name": "UniqueTOI", "values": ["true"]},
                ],
            }
        ]
    }
    params = opensearch.get_additional_parameters(data)
    assert ("UniqueAOI", ["true"]) in params
    assert ("UniqueTOI", ["true"]) in params


def get_template_urls(collection_id):
    settings = {
        "weaver.request_options": {
            "requests": [
                # description schema can be *extremely* slow to respond, but it does eventually
                {"url": "http://geo.spacebel.be/opensearch/description.xml", "method": "get", "timeout": 180}
            ]
        }
    }
    all_fields = set()
    opq = opensearch.OpenSearchQuery(collection_id, osdd_url=OSDD_URL, settings=settings)
    template = opq.get_template_url()
    params = parse_qsl(urlparse(template).query)
    param_names = list(sorted(p[0] for p in params))
    if all_fields:
        all_fields = all_fields.intersection(param_names)
    else:
        all_fields.update(param_names)

    fields_in_all_queries = list(sorted(all_fields))
    expected = [
        "bbox",
        "endDate",
        "geometry",
        "httpAccept",
        "lat",
        "lon",
        "maximumRecords",
        "name",
        "parentIdentifier",
        "radius",
        "startDate",
        "startRecord",
        "uid",
    ]
    assert not set(expected) - set(fields_in_all_queries)


@pytest.mark.slow
@pytest.mark.online
@pytest.mark.testbed14
def test_get_template_sentinel2():
    get_template_urls(COLLECTION_IDS["sentinel2"])


@pytest.mark.xfail(reason="Collection 'probav' dataset series cannot be found.")
@pytest.mark.online
@pytest.mark.testbed14
def test_get_template_probav():
    get_template_urls(COLLECTION_IDS["probav"])


def inputs_unique_aoi_toi(files_id):
    return {
        OPENSEARCH_AOI: deque([LiteralInput(OPENSEARCH_AOI, "Area", data_type="string")]),
        OPENSEARCH_START_DATE: deque(
            [LiteralInput(OPENSEARCH_START_DATE, "Start Date", data_type="string")]
        ),
        OPENSEARCH_END_DATE: deque([LiteralInput(OPENSEARCH_END_DATE, "End Date", data_type="string")]),
        files_id: deque(
            [LiteralInput(files_id, "Collection of the data.", data_type="string", max_occurs=4)]
        ),
    }


def inputs_non_unique_aoi_toi(files_id):
    end_date = _make_specific_identifier(OPENSEARCH_END_DATE, files_id)
    start_date = _make_specific_identifier(OPENSEARCH_START_DATE, files_id)
    aoi = _make_specific_identifier(OPENSEARCH_AOI, files_id)
    return {
        aoi: deque([LiteralInput(aoi, "Area", data_type="string")]),
        start_date: deque([LiteralInput(start_date, "Area", data_type="string")]),
        end_date: deque([LiteralInput(end_date, "Area", data_type="string")]),
        files_id: deque(
            [LiteralInput(files_id, "Collection of the data.", data_type="string", max_occurs=4)]
        ),
    }


def query_param_names(unique_aoi_toi, identifier):
    end_date, start_date, aoi = OPENSEARCH_END_DATE, OPENSEARCH_START_DATE, OPENSEARCH_AOI
    if not unique_aoi_toi:
        end_date = _make_specific_identifier(end_date, identifier)
        start_date = _make_specific_identifier(start_date, identifier)
        aoi = _make_specific_identifier(aoi, identifier)
    return end_date, start_date, aoi


def sentinel2_inputs(unique_aoi_toi=True):
    sentinel_id = "image-sentinel2"
    end_date, start_date, aoi = query_param_names(unique_aoi_toi, sentinel_id)
    if unique_aoi_toi:
        inputs = inputs_unique_aoi_toi(sentinel_id)
    else:
        inputs = inputs_non_unique_aoi_toi(sentinel_id)

    inputs[sentinel_id][0].data = COLLECTION_IDS["sentinel2"]
    inputs[end_date][0].data = u"2018-01-31T23:59:59.999Z"
    inputs[start_date][0].data = u"2018-01-30T00:00:00.000Z"
    # inputs[aoi][0].data = u"POLYGON ((100 15, 104 15, 104 19, 100 19, 100 15))"
    inputs[aoi][0].data = u"100.0, 15.0, 104.0, 19.0"

    eo_image_source_info = make_eo_image_source_info(sentinel_id, COLLECTION_IDS["sentinel2"])
    return inputs, eo_image_source_info


def probav_inputs(unique_aoi_toi=True):
    probav_id = "image-probav"
    end_date, start_date, aoi = query_param_names(unique_aoi_toi, probav_id)
    if unique_aoi_toi:
        inputs = inputs_unique_aoi_toi(probav_id)
    else:
        inputs = inputs_non_unique_aoi_toi(probav_id)

    inputs[probav_id][0].data = COLLECTION_IDS["probav"]
    inputs[end_date][0].data = u"2018-01-31T23:59:59.999Z"
    inputs[start_date][0].data = u"2018-01-30T00:00:00.000Z"
    # inputs[aoi][0].data = u"POLYGON ((100 15, 104 15, 104 19, 100 19, 100 15))"
    inputs[aoi][0].data = u"100.0, 15.0, 104.0, 19.0"

    eo_image_source_info = make_eo_image_source_info(
        probav_id, COLLECTION_IDS["probav"]
    )

    return inputs, eo_image_source_info


def make_eo_image_source_info(name, collection_id):
    return {
        name: {
            "collection_id": collection_id,
            "accept_schemes": ["http", "https"],
            "mime_types": ["application/zip"],
            "rootdir": "",
            "ades": "http://localhost:5001",
            "osdd_url": "http://geo.spacebel.be/opensearch/description.xml",
        }
    }


def deimos_inputs(unique_aoi_toi=True):
    deimos_id = "image-deimos"
    end_date, start_date, aoi = query_param_names(unique_aoi_toi, deimos_id)
    inputs = inputs_unique_aoi_toi(deimos_id)

    inputs[deimos_id][0].data = COLLECTION_IDS["deimos"]
    inputs[start_date][0].data = u"2008-01-01T00:00:00Z"
    inputs[end_date][0].data = u"2009-01-01T00:00:00Z"
    # inputs[aoi][0].data = u"MULTIPOINT ((-117 32), (-115 34))"
    inputs[aoi][0].data = u"-117, 32, -115, 34"

    eo_image_source_info = make_eo_image_source_info(deimos_id, COLLECTION_IDS["deimos"])
    return inputs, eo_image_source_info


@pytest.mark.xfail(reason="Record not available anymore although server still up and reachable.")
@pytest.mark.online
@pytest.mark.testbed14
def test_query_sentinel2():
    inputs, eo_image_source_info = sentinel2_inputs()
    mime_types = {k: eo_image_source_info[k]["mime_types"] for k in eo_image_source_info}
    data = opensearch.query_eo_images_from_wps_inputs(inputs, eo_image_source_info, mime_types)

    assert len(data["image-sentinel2"]) == inputs["image-sentinel2"][0].max_occurs


@pytest.mark.xfail(reason="Cannot login to protected 'probav' opensearch endpoint.")
@pytest.mark.online
@pytest.mark.testbed14
def test_query_probav():
    inputs, eo_image_source_info = probav_inputs()
    mime_types = {k: eo_image_source_info[k]["mime_types"] for k in eo_image_source_info}
    data = opensearch.query_eo_images_from_wps_inputs(inputs, eo_image_source_info, mime_types)

    assert len(data["image-probav"]) == inputs["image-probav"][0].max_occurs


@pytest.mark.skip(reason="The server is not implemented yet.")
@pytest.mark.online
@pytest.mark.testbed14
def test_query_deimos():
    inputs, eo_image_source_info = deimos_inputs()
    mime_types = {k: eo_image_source_info[k]["mime_types"] for k in eo_image_source_info}
    data = opensearch.query_eo_images_from_wps_inputs(inputs, eo_image_source_info, mime_types)

    assert len(data["image-deimos"]) == inputs["image-deimos"][0].max_occurs


@pytest.mark.xfail(reason="Cannot login to protected 'probav' opensearch endpoint.")
@pytest.mark.online
@pytest.mark.testbed14
def test_query_non_unique():
    inputs_s2, eo_image_source_info_s2 = sentinel2_inputs(unique_aoi_toi=False)
    inputs_probav, eo_image_source_info_probav = probav_inputs(unique_aoi_toi=False)

    inputs = inputs_s2
    inputs.update(inputs_probav)

    eo_image_source_info = eo_image_source_info_s2
    eo_image_source_info.update(eo_image_source_info_probav)
    mime_types = {k: eo_image_source_info[k]["mime_types"] for k in eo_image_source_info}
    data = opensearch.query_eo_images_from_wps_inputs(inputs, eo_image_source_info, mime_types)

    assert len(data["image-sentinel2"]) == inputs["image-sentinel2"][0].max_occurs
    assert len(data["image-probav"]) == inputs["image-probav"][0].max_occurs
