import json
from collections import deque
from copy import deepcopy
from itertools import chain

import pytest
import unittest
import os
from pprint import pformat

import urlparse
from mock import mock
from pyramid import testing
from pyramid.testing import DummyRequest

import twitcher
from pywps.inout.inputs import LiteralInput
from twitcher import namesgenerator

from twitcher.datatype import Process
from twitcher.processes import opensearch
from twitcher.store import DB_MEMORY, MemoryProcessStore
from twitcher.wps_restapi.processes import processes

OSDD_URL = "http://geo.spacebel.be/opensearch/description.xml"

COLLECTION_IDS = {
    "sentinel2": "EOP:IPT:Sentinel2",
    "probav": "EOP:VITO:PROBAV_P_V001",
    "deimos": "DE2_PS3_L1C",
}


def assert_json_equals(json1, json2):
    def ordered_json(obj):
        if isinstance(obj, dict):
            return sorted((unicode(k), ordered_json(v)) for k, v in obj.items())
        elif isinstance(obj, list):
            return sorted(ordered_json(x) for x in obj)
        else:
            return unicode(obj)

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
    request.registry.settings["twitcher.url"] = "localhost"
    request.registry.settings["twitcher.db_factory"] = DB_MEMORY
    return request


class WpsHandleEOITestCase(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()


@pytest.fixture
def memory_store():
    hello = twitcher.processes.wps_hello.Hello()
    store = MemoryProcessStore([hello])
    return store


@pytest.fixture
def dummy_payload():
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


@pytest.fixture
def opensearch_payload():
    js = load_json_test_file("opensearch_deploy.json")
    cwl = get_test_file("json_examples", "opensearch_deploy.cwl")
    js["executionUnit"][0]["href"] = cwl
    return js


@pytest.fixture
def opensearch_process():
    opensearch_process = Process(load_json_test_file("opensearch_process.json"))
    return opensearch_process


@pytest.fixture
def memory_store_with_opensearch_process(memory_store, opensearch_process):
    memory_store.save_process(opensearch_process)
    return memory_store


@mock.patch("twitcher.wps_restapi.processes.processes.processstore_factory")
def test_describe_process_opensearch(
    processstore_factory, memory_store, opensearch_process
):
    memory_store.save_process(opensearch_process)
    processstore_factory.return_value = memory_store

    request = make_request(method="GET")
    request.matchdict["process_id"] = namesgenerator.get_sane_name(
        opensearch_process.id
    )

    transformed_inputs = processes.get_local_process(request).json["process"]["inputs"]

    original_inputs = opensearch_process.json()["inputs"]
    expected_inputs = opensearch.replace_inputs_eoimage_files_to_query(
        original_inputs, opensearch_process.payload, wps_inputs=True
    )

    assert_json_equals(transformed_inputs, expected_inputs)


def test_transform_execute_parameters_wps(opensearch_process):
    def make_input(id_, value):
        input_ = LiteralInput(id_, "", data_type="string")
        input_.data = value
        return input_

    def make_deque(id_, value):
        input_ = make_input(id_, value)
        return id_, deque([input_])

    inputs = dict(
        [
            make_deque("startDate", "2018-01-30T00:00:00.000Z"),
            make_deque("endDate", "2018-01-31T23:59:59.999Z"),
            make_deque(
                "aoi",
                "POLYGON ((100.4 15.3, 104.6 15.3, 104.6 19.3, 100.4 19.3, 100.4 15.3))",
            ),
            make_deque("files", "EOP:IPT:Sentinel2"),
            make_deque("output_file_type", "GEOTIFF"),
            make_deque("output_name", "stack_result.tif"),
        ]
    )

    mocked_query = ["file:///something.SAFE"]
    files_inputs = [make_input("files", "opensearch_" + m) for m in mocked_query]

    expected = dict(
        [
            make_deque("output_file_type", "GEOTIFF"),
            make_deque("output_name", "stack_result.tif"),
            ("files", deque(files_inputs)),
        ]
    )

    payload = opensearch_process.payload
    eoimage_ids = opensearch.get_eoimages_ids_from_payload(payload)
    opensearch.OpenSearchQuery.query_datasets = mock.MagicMock()
    opensearch.OpenSearchQuery.query_datasets.return_value = mocked_query

    transformed = opensearch.query_eo_images_from_wps_inputs(
        inputs, eoimage_ids, OSDD_URL
    )

    def compare(items):
        return sorted([(k, [v.data for v in values]) for k, values in items.items()])

    assert compare(transformed) == compare(expected)


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


@mock.patch("twitcher.wps_restapi.processes.processes.processstore_factory")
def test_deploy_opensearch(processstore_factory, opensearch_payload):
    # given
    initial_payload = deepcopy(opensearch_payload)
    request = make_request(json=opensearch_payload, method="POST")
    process_id = opensearch_payload["processDescription"]["process"]["identifier"]

    store = MemoryProcessStore()
    processstore_factory.return_value = store
    # when
    response = processes.add_local_process(request)

    # then
    assert response.code == 200
    assert response.json["deploymentDone"]
    process = store.fetch_by_id(process_id)
    assert process
    assert process.package
    assert process.payload
    assert_json_equals(process.payload, initial_payload)


def test_handle_EOI_unique_aoi_unique_toi():
    inputs = load_json_test_file("eoimage_inputs_example.json")
    expected = load_json_test_file("eoimage_unique_aoi_unique_toi.json")
    output = twitcher.processes.opensearch.EOImageDescribeProcessHandler(
        inputs
    ).to_opensearch(unique_aoi=True, unique_toi=True)
    assert_json_equals(output, expected)


def test_handle_EOI_unique_aoi_non_unique_toi():
    inputs = load_json_test_file("eoimage_inputs_example.json")
    expected = load_json_test_file("eoimage_unique_aoi_non_unique_toi.json")
    output = twitcher.processes.opensearch.EOImageDescribeProcessHandler(
        inputs
    ).to_opensearch(unique_aoi=True, unique_toi=False)
    assert_json_equals(expected, output)


def test_handle_EOI_non_unique_aoi_unique_toi():
    inputs = load_json_test_file("eoimage_inputs_example.json")
    expected = load_json_test_file("eoimage_non_unique_aoi_unique_toi.json")
    output = twitcher.processes.opensearch.EOImageDescribeProcessHandler(
        inputs
    ).to_opensearch(unique_aoi=False, unique_toi=True)
    assert_json_equals(expected, output)


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
    params = twitcher.processes.opensearch.get_additional_parameters(data)
    assert ("UniqueAOI", ["true"]) in params
    assert ("UniqueTOI", ["true"]) in params


@pytest.mark.online
def test_get_template_urls():
    all_fields = set()
    for name, collection_id in COLLECTION_IDS.items():
        o = opensearch.OpenSearchQuery(collection_id, osdd_url=OSDD_URL)
        template = o.get_template_url()
        params = urlparse.parse_qsl(urlparse.urlparse(template).query)
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
    assert fields_in_all_queries == expected


@pytest.mark.online
def test_query():
    eoimage_ids = ["files"]
    osdd_url = "http://geo.spacebel.be/opensearch/description.xml"
    inputs = {
        "aoi": deque([LiteralInput("aoi", "Area", data_type="string")]),
        "startDate": deque([LiteralInput("startDate", "Area", data_type="string")]),
        "endDate": deque([LiteralInput("endDate", "Area", data_type="string")]),
        "files": deque(
            [LiteralInput("files", "Collection id to query", data_type="string")]
        ),
    }

    inputs["files"][0].data = "EOP:IPT:Sentinel2"
    inputs["endDate"][0].data = u"2018-01-31T23:59:59.999Z"
    inputs["startDate"][0].data = u"2018-01-30T00:00:00.000Z"
    inputs["aoi"][0].data = u"POLYGON ((100 15, 104 15, 104 19, 100 19, 100 15))"

    data = opensearch.query_eo_images_from_wps_inputs(
        inputs, eoimage_ids, osdd_url, accept_schemes=("file", "https")
    )

    assert len(data["files"]) == 15

    inputs["files"][0].data = "EOP:VITO:PROBAV_P_V001"
    inputs["endDate"][0].data = u"2018-01-31T23:59:59.999Z"
    inputs["startDate"][0].data = u"2018-01-30T00:00:00.000Z"
    inputs["aoi"][0].data = u"POLYGON ((100 15, 104 15, 104 19, 100 19, 100 15))"
    #
    data = opensearch.query_eo_images_from_wps_inputs(
        inputs, eoimage_ids, osdd_url, accept_schemes=("file", "https")
    )

    assert len(data["files"]) == 3

    # Not implemented
    # inputs["files"][0].data = "DE2_PS3_L1C"
    # inputs["startDate"][0].data = u'2008-01-01T00:00:00Z'
    # inputs["endDate"][0].data = u'2009-01-01T00:00:00Z'
    # inputs["aoi"][0].data = u'MULTIPOINT ((-117 32), (-115 34))'
    # "http://geo.spacebel.be/opensearch/request?parentIdentifier=DE2_PS3_L1C&bbox=-117%2C32.7%2C-115%2C33.45&startDate=2008-01-01T00:00:00Z&endDate=2009-01-01T00:00:00Z"

    # data = opensearch.query_eo_images_from_wps_inputs(inputs, eoimage_ids, osdd_url,
    #                                                   accept_schemes=("file", "https"))

    # assert len(data["files"]) == 8
