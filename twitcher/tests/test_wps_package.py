import json
import pytest
import unittest
import os
from pprint import pformat

from pyramid import testing
from pyramid.testing import DummyRequest

from twitcher.processes import wps_package
from twitcher.store import DB_MEMORY


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


def get_test_file(filename):
    return os.path.join(os.path.dirname(__file__), 'json_examples', filename)


def load_json(filename):
    return json.load(open(get_test_file(filename)))


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

    def test_handle_EOI_unique_aoi_unique_toi(self):
        inputs = load_json("eoimage_inputs_example.json")
        expected = load_json("eoimage_unique_aoi_unique_toi.json")
        output = wps_package.EOImageHandler(inputs).to_opensearch(unique_aoi=True, unique_toi=True)
        assert_json_equals(output, expected)

    def test_handle_EOI_unique_aoi_non_unique_toi(self):
        inputs = load_json("eoimage_inputs_example.json")
        expected = load_json("eoimage_unique_aoi_non_unique_toi.json")
        output = wps_package.EOImageHandler(inputs).to_opensearch(unique_aoi=True, unique_toi=False)
        assert_json_equals(expected, output)

    def test_handle_EOI_non_unique_aoi_unique_toi(self):
        inputs = load_json("eoimage_inputs_example.json")
        expected = load_json("eoimage_non_unique_aoi_unique_toi.json")
        output = wps_package.EOImageHandler(inputs).to_opensearch(unique_aoi=False, unique_toi=True)
        assert_json_equals(expected, output)

    def test_handle_EOI_multisensor_ndvi(self):
        deploy = load_json("DeployProcess_Workflow_MultiSensor_NDVI_Stack_Generator_.json")
        inputs = deploy["processOffering"]["process"]["inputs"]
        describe = load_json("DescribeProcessResponse_Multisensor_ndivi_stack_generator.json")
        expected = describe["processOffering"]["process"]["inputs"]
        output = wps_package.EOImageHandler(inputs).to_opensearch(unique_aoi=True, unique_toi=True)
        assert_json_equals(expected, output)

    def test_get_additional_parameters(self):
        data = {"additionalParameters": [{"role": "http://www.opengis.net/eoc/applicationContext",
                                          "parameters": [{"name": "UniqueAOI", "value": "true"},
                                                         {"name": "UniqueTOI", "value": "true"}]}]}
        params = wps_package.get_additional_parameters(data)
        assert ("UniqueAOI", "true") in params
        assert ("UniqueTOI", "true") in params
