import json
import pytest
import unittest
import os
from pprint import pformat

from mock import mock
from pyramid import testing
from pyramid.testing import DummyRequest

import twitcher

from twitcher.datatype import Process
from twitcher.processes import wps_package, Package
from twitcher.store import DB_MEMORY, MemoryProcessStore
from twitcher.wps_restapi.processes import processes


def add_pywps_path():
    import sys
    here = os.path.dirname(__file__)
    while not here.endswith("testbed14-twitcher"):
        here = os.path.dirname(here)
    sys.path.append(os.path.join(here, "src", "pywps"))


from pywps.app.Service import Service


def assert_json_equals(json1, json2):
    def ordered_json(obj):
        if isinstance(obj, dict):
            return sorted((k, ordered_json(v)) for k, v in obj.items())
        elif isinstance(obj, list):
            return sorted(ordered_json(x) for x in obj)
        else:
            return obj

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
    request.registry.settings['twitcher.url'] = "localhost"
    request.registry.settings['twitcher.db_factory'] = DB_MEMORY
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
    return {"processOffering": {"process": {
        "identifier": "workflow_stacker_sfs_id",
        "title": "Application StackCreation followed by SFS dynamically added by POST /processes",
        "owsContext": {
            "offering": {"code": "http://www.opengis.net/eoc/applicationContext/cwl",
                         "content": {"href": "http://some.host/applications/cwl/multisensor_ndvi.cwl"}}
        }
    }}}


@pytest.fixture
def opensearch_payload():
    return load_json_test_file("opensearch_deploy.json")


@pytest.fixture
def opensearch_process():
    opensearch_process = Process(load_json_test_file("opensearch_package.json"))
    payload = load_json_test_file("opensearch_deploy.json")
    opensearch_process["payload"] = payload
    return opensearch_process


@pytest.fixture
def store_with_opensearch_process(memory_store, opensearch_process):
    memory_store.save_process(opensearch_process)
    return memory_store


def test_deploy_opensearch():
    pass


@mock.patch("twitcher.wps_restapi.processes.processes.processstore_defaultfactory")
def test_describe_process_opensearch(default_factory, memory_store, opensearch_process):
    memory_store.save_process(opensearch_process)
    default_factory.return_value = memory_store

    payload = load_json_test_file("opensearch_deploy.json")

    request = make_request(method='GET')
    request.matchdict["process_id"] = "multi_sensor_ndvi_stack_g"

    original_inputs = payload["processOffering"]["process"]["inputs"]
    transformed_inputs = processes.get_local_process(request).json["process"]["inputs"]

    expected_inputs = wps_package.EOImageHandler(inputs=original_inputs).to_opensearch(
        unique_aoi=True, unique_toi=True)

    assert_json_equals(transformed_inputs, expected_inputs)


@mock.patch("twitcher.wps_restapi.processes.processes.processstore_defaultfactory")
def test_execute_opensearch(default_factory, memory_store, opensearch_process):
    # opensearch_process.executeEndpoint = "localhost"
    memory_store.save_process(opensearch_process)
    default_factory.return_value = memory_store

    request = make_request(method='POST')
    request.matchdict["process_id"] = "multi_sensor_ndvi_stack_g"

    response = processes.submit_local_job(request)


@mock.patch("twitcher.wps_restapi.processes.processes.wps_package.get_process_from_wps_request")
@mock.patch("twitcher.wps_restapi.processes.processes.processstore_defaultfactory")
def test_deploy_opensearch(default_factory, mock_get_process, opensearch_payload):
    # given
    dummy_process_offering = {"package": "", "type": "", "inputs": "", "outputs": ""}
    dummy_process_offering.update(opensearch_payload["processOffering"]["process"])
    mock_get_process.return_value = dummy_process_offering
    request = make_request(json=opensearch_payload, method='POST')

    store = MemoryProcessStore()
    store.save_process = mock.MagicMock()
    default_factory.return_value = store
    # when
    response = processes.add_local_process(request)

    # then
    assert response.code == 200
    assert response.json["deploymentDone"]
    assert store.save_process.called
    package = store.save_process.call_args[0][0]
    assert "package" in package


def test_handle_EOI_unique_aoi_unique_toi():
    inputs = load_json_test_file("eoimage_inputs_example.json")
    expected = load_json_test_file("eoimage_unique_aoi_unique_toi.json")
    output = wps_package.EOImageHandler(inputs).to_opensearch(unique_aoi=True, unique_toi=True)
    assert_json_equals(output, expected)


def test_handle_EOI_unique_aoi_non_unique_toi():
    inputs = load_json_test_file("eoimage_inputs_example.json")
    expected = load_json_test_file("eoimage_unique_aoi_non_unique_toi.json")
    output = wps_package.EOImageHandler(inputs).to_opensearch(unique_aoi=True, unique_toi=False)
    assert_json_equals(expected, output)


def test_handle_EOI_non_unique_aoi_unique_toi():
    inputs = load_json_test_file("eoimage_inputs_example.json")
    expected = load_json_test_file("eoimage_non_unique_aoi_unique_toi.json")
    output = wps_package.EOImageHandler(inputs).to_opensearch(unique_aoi=False, unique_toi=True)
    assert_json_equals(expected, output)


def test_handle_EOI_multisensor_ndvi():
    deploy = load_json_test_file("DeployProcess_Workflow_MultiSensor_NDVI_Stack_Generator_.json")
    inputs = deploy["processOffering"]["process"]["inputs"]
    describe = load_json_test_file("DescribeProcessResponse_Multisensor_ndivi_stack_generator.json")
    expected = describe["processOffering"]["process"]["inputs"]
    output = wps_package.EOImageHandler(inputs).to_opensearch(unique_aoi=True, unique_toi=True)
    assert_json_equals(expected, output)


def test_get_additional_parameters():
    data = {"additionalParameters": [{"role": "http://www.opengis.net/eoc/applicationContext",
                                      "parameters": [{"name": "UniqueAOI", "value": "true"},
                                                     {"name": "UniqueTOI", "value": "true"}]}]}
    params = wps_package.get_additional_parameters(data)
    assert ("UniqueAOI", "true") in params
    assert ("UniqueTOI", "true") in params
