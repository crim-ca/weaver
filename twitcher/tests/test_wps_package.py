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


class WpsHandleEOITestCase(unittest.TestCase):
    def setUp(self):
        self.config = testing.setUp()

    def tearDown(self):
        testing.tearDown()

    def get_workflow_file(self, filename):
        return open(os.path.join(os.path.dirname(__file__), '..', 'workflows', filename)).read()

    def make_request(self, **kw):
        request = DummyRequest(**kw)
        request.registry.settings['twitcher.url'] = "localhost"
        request.registry.settings['twitcher.db_factory'] = DB_MEMORY
        return request

    def test_handle_EOI_unique_aoi_unique_toi(self):
        inputs = [{"id": "image-s2",
                   "title": "S2 Input Image",
                   "formats": [{"mimeType": "application/zip", "default": True}],
                   "minOccurs": 1,
                   "maxOccurs": "unbounded",
                   "additionalParameters":
                       [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                         "parameters":
                             [{"name": "EOImage",
                               "value": "true"},
                              {"name": "AllowedCollections",
                               "value": "s2-collection-1,s2-collection-2,s2-sentinel2,s2-landsat8"}]
                         }]},
                  {"id": "image-probav",
                   "title": "ProbaV Input Image",
                   "formats": [{"mimeType": "application/zip", "default": True}],
                   "minOccurs": 1,
                   "maxOccurs": "unbounded",
                   "additionalParameters":
                       [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                         "parameters": [{"name": "EOImage", "value": "true"},
                                        {"name": "AllowedCollections",
                                         "value": "probav-collection-1,probav-collection-2"}]
                         }]},
                  ]
        expected = [{"id": "aoi",
                     "title": "Area of Interest",
                     "abstract": "Area of Interest (Bounding Box)",
                     "formats": [{"mimeType": "OGC-WKT", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1
                     },
                    {"id": "StartDate",
                     "title": "Time of Interest",
                     "abstract": "Time of Interest (defined as Start date - End date)",
                     "formats": [{"mimeType": "text/plain", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1,
                     "LiteralDataDomain": {"dataType": "String"},
                     "additionalParameters":
                         [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                           "parameters": [{"name": "CatalogSearchField",
                                           "value": "startDate"}]
                           }],
                     "owsContext": {"offering": {"code": "anyCode", "content": {"href": "anyRef"}}}},
                    {"id": "EndDate",
                     "title": "Time of Interest",
                     "abstract": "Time of Interest (defined as Start date - End date)",
                     "formats": [{"mimeType": "text/plain", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1,
                     "LiteralDataDomain": {"dataType": "String"},
                     "additionalParameters":
                         [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                           "parameters": [{"name": "CatalogSearchField", "value": "endDate"}]
                           }],
                     "owsContext": {"offering": {"code": "anyCode", "content": {"href": "anyRef"}}}},
                    {"id": "collectionId_image-s2",
                     "title": "Collection of the data.",
                     "abstract": "Collection",
                     "formats": [{"mimeType": "text/plain", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1,
                     "LiteralDataDomain": {"dataType": "String",
                                           "allowedValues": ['s2-collection-1', 's2-collection-2', 's2-landsat8',
                                                             's2-sentinel2']},
                     "additionalParameters":
                         [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                           "parameters": [{"name": "CatalogSearchField", "value": "parentIdentifier"}]
                           }],
                     "owsContext": {"offering": {"code": "anyCode", "content": {"href": "anyRef"}}}},
                    {"id": "collectionId_image-probav",
                     "title": "Collection of the data.",
                     "abstract": "Collection",
                     "formats": [{"mimeType": "text/plain", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1,
                     "LiteralDataDomain": {"dataType": "String",
                                           "allowedValues": ["probav-collection-1", "probav-collection-2"]},
                     "additionalParameters":
                         [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                           "parameters": [{"name": "CatalogSearchField", "value": "parentIdentifier"}]
                           }],
                     "owsContext": {"offering": {"code": "anyCode", "content": {"href": "anyRef"}}}},
                    ]
        output = wps_package.EOImageHandler(inputs).to_opensearch(unique_aoi=True, unique_toi=True)
        assert_json_equals(output, expected)

    def test_handle_EOI_unique_aoi_non_unique_toi(self):
        inputs = [{"id": "image-s2",
                   "title": "S2 Input Image",
                   "formats": [{"mimeType": "application/zip", "default": True}],
                   "minOccurs": 1,
                   "maxOccurs": "unbounded",
                   "additionalParameters":
                       [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                         "parameters":
                             [{"name": "EOImage",
                               "value": "true"},
                              {"name": "AllowedCollections",
                               "value": "s2-collection-1,s2-collection-2,s2-sentinel2,s2-landsat8"}]
                         }]},
                  {"id": "image-probav",
                   "title": "ProbaV Input Image",
                   "formats": [{"mimeType": "application/zip", "default": True}],
                   "minOccurs": 1,
                   "maxOccurs": "unbounded",
                   "additionalParameters":
                       [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                         "parameters": [{"name": "EOImage", "value": "true"},
                                        {"name": "AllowedCollections",
                                         "value": "probav-collection-1,probav-collection-2"}]
                         }]},
                  ]
        expected = [{"id": "aoi",
                     "title": "Area of Interest",
                     "abstract": "Area of Interest (Bounding Box)",
                     "formats": [{"mimeType": "OGC-WKT", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1
                     },
                    {"id": "StartDate_image-s2",
                     "title": "Time of Interest",
                     "abstract": "Time of Interest (defined as Start date - End date)",
                     "formats": [{"mimeType": "text/plain", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1,
                     "LiteralDataDomain": {"dataType": "String"},
                     "additionalParameters":
                         [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                           "parameters": [{"name": "CatalogSearchField",
                                           "value": "startDate"}]
                           }],
                     "owsContext": {"offering": {"code": "anyCode", "content": {"href": "anyRef"}}}},
                    {"id": "EndDate_image-s2",
                     "title": "Time of Interest",
                     "abstract": "Time of Interest (defined as Start date - End date)",
                     "formats": [{"mimeType": "text/plain", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1,
                     "LiteralDataDomain": {"dataType": "String"},
                     "additionalParameters":
                         [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                           "parameters": [{"name": "CatalogSearchField", "value": "endDate"}]
                           }],
                     "owsContext": {"offering": {"code": "anyCode", "content": {"href": "anyRef"}}}},
                    {"id": "StartDate_image-probav",
                     "title": "Time of Interest",
                     "abstract": "Time of Interest (defined as Start date - End date)",
                     "formats": [{"mimeType": "text/plain", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1,
                     "LiteralDataDomain": {"dataType": "String"},
                     "additionalParameters":
                         [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                           "parameters": [{"name": "CatalogSearchField",
                                           "value": "startDate"}]
                           }],
                     "owsContext": {"offering": {"code": "anyCode", "content": {"href": "anyRef"}}}},
                    {"id": "EndDate_image-probav",
                     "title": "Time of Interest",
                     "abstract": "Time of Interest (defined as Start date - End date)",
                     "formats": [{"mimeType": "text/plain", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1,
                     "LiteralDataDomain": {"dataType": "String"},
                     "additionalParameters":
                         [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                           "parameters": [{"name": "CatalogSearchField", "value": "endDate"}]
                           }],
                     "owsContext": {"offering": {"code": "anyCode", "content": {"href": "anyRef"}}}},
                    {"id": "collectionId_image-s2",
                     "title": "Collection of the data.",
                     "abstract": "Collection",
                     "formats": [{"mimeType": "text/plain", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1,
                     "LiteralDataDomain": {"dataType": "String",
                                           "allowedValues": ['s2-collection-1', 's2-collection-2', 's2-landsat8',
                                                             's2-sentinel2']},
                     "additionalParameters":
                         [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                           "parameters": [{"name": "CatalogSearchField", "value": "parentIdentifier"}]
                           }],
                     "owsContext": {"offering": {"code": "anyCode", "content": {"href": "anyRef"}}}},
                    {"id": "collectionId_image-probav",
                     "title": "Collection of the data.",
                     "abstract": "Collection",
                     "formats": [{"mimeType": "text/plain", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1,
                     "LiteralDataDomain": {"dataType": "String",
                                           "allowedValues": ["probav-collection-1", "probav-collection-2"]},
                     "additionalParameters":
                         [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                           "parameters": [{"name": "CatalogSearchField", "value": "parentIdentifier"}]
                           }],
                     "owsContext": {"offering": {"code": "anyCode", "content": {"href": "anyRef"}}}},
                    ]
        output = wps_package.EOImageHandler(inputs).to_opensearch(unique_aoi=True, unique_toi=False)
        assert_json_equals(expected, output)

    def test_handle_EOI_non_unique_aoi_unique_toi(self):
        inputs = [{"id": "image-s2",
                   "title": "S2 Input Image",
                   "formats": [{"mimeType": "application/zip", "default": True}],
                   "minOccurs": 1,
                   "maxOccurs": "unbounded",
                   "additionalParameters":
                       [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                         "parameters":
                             [{"name": "EOImage",
                               "value": "true"},
                              {"name": "AllowedCollections",
                               "value": "s2-collection-1,s2-collection-2,s2-sentinel2,s2-landsat8"}]
                         }]},
                  {"id": "image-probav",
                   "title": "ProbaV Input Image",
                   "formats": [{"mimeType": "application/zip", "default": True}],
                   "minOccurs": 1,
                   "maxOccurs": "unbounded",
                   "additionalParameters":
                       [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                         "parameters": [{"name": "EOImage", "value": "true"},
                                        {"name": "AllowedCollections",
                                         "value": "probav-collection-1,probav-collection-2"}]
                         }]},
                  ]
        expected = [{"id": "aoi_image-probav",
                     "title": "Area of Interest",
                     "abstract": "Area of Interest (Bounding Box)",
                     "formats": [{"mimeType": "OGC-WKT", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1
                     },
                    {"id": "aoi_image-s2",
                     "title": "Area of Interest",
                     "abstract": "Area of Interest (Bounding Box)",
                     "formats": [{"mimeType": "OGC-WKT", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1
                     },
                    {"id": "StartDate",
                     "title": "Time of Interest",
                     "abstract": "Time of Interest (defined as Start date - End date)",
                     "formats": [{"mimeType": "text/plain", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1,
                     "LiteralDataDomain": {"dataType": "String"},
                     "additionalParameters":
                         [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                           "parameters": [{"name": "CatalogSearchField",
                                           "value": "startDate"}]
                           }],
                     "owsContext": {"offering": {"code": "anyCode", "content": {"href": "anyRef"}}}},
                    {"id": "EndDate",
                     "title": "Time of Interest",
                     "abstract": "Time of Interest (defined as Start date - End date)",
                     "formats": [{"mimeType": "text/plain", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1,
                     "LiteralDataDomain": {"dataType": "String"},
                     "additionalParameters":
                         [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                           "parameters": [{"name": "CatalogSearchField", "value": "endDate"}]
                           }],
                     "owsContext": {"offering": {"code": "anyCode", "content": {"href": "anyRef"}}}},
                    {"id": "collectionId_image-s2",
                     "title": "Collection of the data.",
                     "abstract": "Collection",
                     "formats": [{"mimeType": "text/plain", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1,
                     "LiteralDataDomain": {"dataType": "String",
                                           "allowedValues": ['s2-collection-1', 's2-collection-2', 's2-landsat8',
                                                             's2-sentinel2']},
                     "additionalParameters":
                         [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                           "parameters": [{"name": "CatalogSearchField", "value": "parentIdentifier"}]
                           }],
                     "owsContext": {"offering": {"code": "anyCode", "content": {"href": "anyRef"}}}},
                    {"id": "collectionId_image-probav",
                     "title": "Collection of the data.",
                     "abstract": "Collection",
                     "formats": [{"mimeType": "text/plain", "default": True}],
                     "minOccurs": 1,
                     "maxOccurs": 1,
                     "LiteralDataDomain": {"dataType": "String",
                                           "allowedValues": ["probav-collection-1", "probav-collection-2"]},
                     "additionalParameters":
                         [{"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                           "parameters": [{"name": "CatalogSearchField", "value": "parentIdentifier"}]
                           }],
                     "owsContext": {"offering": {"code": "anyCode", "content": {"href": "anyRef"}}}},
                    ]
        output = wps_package.EOImageHandler(inputs).to_opensearch(unique_aoi=False, unique_toi=True)
        assert_json_equals(expected, output)

    def test_get_additional_parameters(self):
        data = {"additionalParameters": [{"role": "http://www.opengis.net/eoc/applicationContext",
                                          "parameters": [{"name": "UniqueAOI", "value": "true"},
                                                         {"name": "UniqueTOI", "value": "true"}]}]}
        params = wps_package.get_additional_parameters(data)
        assert ("UniqueAOI", "true") in params
        assert ("UniqueTOI", "true") in params
