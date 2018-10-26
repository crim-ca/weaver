import time
from collections import deque
from copy import deepcopy
from itertools import ifilterfalse
from twitcher.utils import get_any_id
from pyramid.settings import asbool

import lxml.etree
import requests
import urlparse
import shapely.wkt

from typing import Iterable, Dict, Tuple, List, Deque
import logging

from twitcher.processes.wps_process import OPENSEARCH_LOCAL_FILE_SCHEME

LOGGER = logging.getLogger("PACKAGE")


def query_eo_images_from_wps_inputs(
    wps_inputs, eoimage_ids, osdd_url, accept_schemes=("http", "https")
):
    # type: (Dict[str, Deque], Iterable, str, Tuple) -> Dict[str, Deque]
    """Query OpenSearch using parameters in inputs and return file links.

    eoimage_ids is used to identify if a certain input is an eoimage.
    todo: handle non unique aoi and toi

    Args:
        wps_inputs: inputs containing info to query
        eoimage_ids: strings representing the name of fields that are EOImages
        osdd_url: base OSDD url to query
        accept_schemes: return result only for these schemes
    """

    new_inputs = deepcopy(wps_inputs)

    def pop_first_input(id_to_pop):
        return new_inputs.pop(id_to_pop)

    eoimages_inputs = [input_id for input_id in wps_inputs if input_id in eoimage_ids]
    if eoimages_inputs:
        eoimages_queue = deque()
        for input_id, queue in wps_inputs.items():
            if input_id in eoimage_ids:
                new_inputs.pop(input_id)

                wkt = pop_first_input("aoi")[0].data
                bbox_str = load_wkt(wkt)

                params = {
                    "startDate": pop_first_input("startDate")[0].data,
                    "endDate": pop_first_input("endDate")[0].data,
                    "bbox": bbox_str,
                }
                os = OpenSearchQuery(
                    collection_identifier=queue[0].data, osdd_url=osdd_url
                )

                for link in os.query_datasets(params, accept_schemes):
                    new_input = deepcopy(queue[0])
                    new_input.data = replace_with_opensearch_scheme(link)
                    eoimages_queue.append(new_input)

        # todo: we take the first one for now, change to handle non unique aoi and toi
        eoimage_input_name = eoimages_inputs[0]
        new_inputs[eoimage_input_name] = eoimages_queue
    return new_inputs


def replace_with_opensearch_scheme(link):
    """
    Args:
        link: url to replace scheme
    """
    scheme = urlparse.urlparse(link).scheme
    if scheme == "file":
        link_without_scheme = link[link.find(":") :]
        return "{}{}".format(OPENSEARCH_LOCAL_FILE_SCHEME, link_without_scheme)
    else:
        return link


def load_wkt(wkt):
    """
    Args:
        wkt (string): to get the bounding box of
    """
    bounds = shapely.wkt.loads(wkt).bounds
    bbox_str = ",".join(map(str, bounds))
    return bbox_str


class OpenSearchQuery(object):
    MAX_QUERY_RESULTS = 10  # usually the default at the OpenSearch server too

    def __init__(
        self,
        collection_identifier,  # type: str
        osdd_url,  # type: str
        catalog_search_field="parentIdentifier",  # type: str
    ):
        """
        Args:
            collection_identifier: Collection ID to query
            osdd_url: Global OSDD url for opensearch queries.
            catalog_search_field: Name of the field for the collection
                identifier.
        """
        self.collection_identifier = collection_identifier
        self.osdd_url = osdd_url
        self.params = {
            catalog_search_field: collection_identifier,
            "httpAccept": "application/geo+json",
        }
        # validate inputs
        if any(c in "/?" for c in collection_identifier):
            raise ValueError(
                "Invalid collection identifier: {}".format(collection_identifier)
            )

    def get_template_url(self):
        r = requests.get(self.osdd_url, params=self.params)
        r.raise_for_status()

        et = lxml.etree.fromstring(r.content)
        xpath = "//*[local-name() = 'Url'][@rel='results']"
        url = et.xpath(xpath)[0]  # type: lxml.etree._Element
        return url.attrib["template"]

    def _prepare_query_url(self, template_url, params):
        # type: (str, Dict) -> Tuple[str, Dict]
        """
        Args:
            template_url: url containing query parameters
            params: parameters to insert in formated url
        """
        base_url, query = template_url.split("?", 1)

        query_params = {}
        template_parameters = urlparse.parse_qsl(query)

        allowed_names = set([p[0] for p in template_parameters])
        for key, value in template_parameters:
            if "{" in value and "}" in value:
                pass
            else:  # default value
                query_params[key] = value

        for key, value in params.items():
            if key not in allowed_names:
                # todo: raise twitcher-specific exception
                raise ValueError(
                    "{key} is not an allowed query parameter".format(key=key)
                )
            query_params[key] = value

        query_params["maximumRecords"] = self.MAX_QUERY_RESULTS

        return base_url, query_params

    def requests_get_retry(self, *args, **kwargs):
        """Retry a requests.get call

        Args:
            *args: passed to requests.get
            **kwargs: passed to requests.get
        """
        retries_in_secs = [1, 5]
        for wait in retries_in_secs:
            response = requests.get(*args, **kwargs)
            if response.status_code == 200:
                return response
            else:
                time.sleep(wait)
        return response

    def _query_features_paginated(self, params):
        # type: (Dict) -> Iterable[Dict, str]
        """
        Args:
            params: query parameters
        """
        start_index = 1
        template_url = self.get_template_url()
        base_url, query_params = self._prepare_query_url(template_url, params)
        while True:
            query_params["startRecord"] = start_index
            response = self.requests_get_retry(base_url, params=query_params)
            if not response.status_code == 200:
                break
            json_body = response.json()
            features = json_body.get("features", [])
            for feature in features:
                yield feature, response.url
            n_received_features = len(features)
            total_results = json_body["totalResults"]
            if not n_received_features:
                break
            if start_index + n_received_features > total_results:
                break
            start_index += n_received_features

    def query_datasets(self, params, accept_schemes):
        # type: (Dict, Tuple) -> Iterable
        """
        Args:
            params: query parameters
            accept_schemes: only return links of this scheme
        """
        if params is None:
            params = {}

        for feature, url in self._query_features_paginated(params):
            try:
                data_links = [d["href"] for d in feature["properties"]["links"]["data"]]
            except KeyError:
                LOGGER.exception("Badly formatted json at: {}".format(url))
                raise

            for link in data_links:
                scheme = urlparse.urlparse(link).scheme
                if scheme in accept_schemes:
                    yield link
                    continue
                else:
                    LOGGER.debug("No accepted scheme for feature at: {}".format(url))


def get_additional_parameters(input_data):
    # type: (Dict) -> List[Tuple[str, str]]
    """
    Args:
        input_data: Dict containing or not the "additionalParameters" key
    """
    output = []
    additional_parameters = input_data.get("additionalParameters", [])
    for additional_param in additional_parameters:
        for key, value in additional_param.items():
            if key == "parameters":
                for param in value:
                    name = param.get("name", "")
                    values = param.get("values", [])
                    if name:
                        output.append((name, values))
    return output


class EOImageDescribeProcessHandler(object):
    def __init__(self, inputs):
        # type: (List[Dict]) -> None
        """
        Args:
            inputs:
        """
        self.eoimage_inputs = list(filter(self.is_eoimage_input, inputs))
        self.other_inputs = list(ifilterfalse(self.is_eoimage_input, inputs))

    @staticmethod
    def is_eoimage_input(input_data):
        # type: (Dict) -> bool
        """
        Args:
            input_data:
        """
        for name, value in get_additional_parameters(input_data):
            if name.upper() == "EOIMAGE" and value and asbool(value[0]):
                return True
        return False

    @staticmethod
    def get_allowed_collections(input_data):
        # type: (Dict) -> List
        """
        Args:
            input_data:
        """
        for name, value in get_additional_parameters(input_data):
            if name.upper() == "ALLOWEDCOLLECTIONS":
                return value.split(",")
        return []

    @staticmethod
    def make_aoi(id_, unbounded):
        """
        Args:
            id_:
            unbounded:
        """
        max_occurs = u"unbounded" if unbounded else 1
        data = {
            u"id": id_,
            u"title": u"Area of Interest",
            u"abstract": u"Area of Interest (Bounding Box)",
            u"formats": [{u"mimeType": u"OGC-WKT", u"default": True}],
            u"minOccurs": 1,
            u"maxOccurs": max_occurs,
        }
        return data

    @staticmethod
    def make_collection(image_format, allowed_values):
        """
        Args:
            image_format:
            allowed_values:
        """
        data = {
            u"id": u"{}".format(image_format),
            u"title": u"Collection Identifer for input {}".format(image_format),
            u"abstract": u"Collection",
            u"formats": [{u"mimeType": u"text/plain", u"default": True}],
            u"minOccurs": 1,
            u"maxOccurs": u"unbounded",
            u"LiteralDataDomain": {
                u"dataType": u"String",
                u"allowedValues": allowed_values,
            },
            u"additionalParameters": [
                {
                    u"role": u"http://www.opengis.net/eoc/applicationContext/inputMetadata",
                    u"parameters": [
                        {u"name": u"CatalogSearchField", u"value": u"parentIdentifier"}
                    ],
                }
            ],
            u"owsContext": {
                u"offering": {u"code": u"anyCode", u"content": {u"href": u"anyRef"}}
            },
        }
        return data

    @staticmethod
    def make_toi(id_, unbounded, start_date=True):
        """
        Args:
            id_:
            unbounded:
            start_date:
        """
        max_occurs = u"unbounded" if unbounded else 1
        date = u"startDate" if start_date else u"endDate"
        data = {
            u"id": id_,
            u"title": u"Time of Interest",
            u"abstract": u"Time of Interest (defined as Start date - End date)",
            u"formats": [{u"mimeType": u"text/plain", u"default": True}],
            u"minOccurs": 1,
            u"maxOccurs": max_occurs,
            u"LiteralDataDomain": {u"dataType": u"String"},
            u"additionalParameters": [
                {
                    u"role": u"http://www.opengis.net/eoc/applicationContext/inputMetadata",
                    u"parameters": [{u"name": u"CatalogSearchField", u"value": date}],
                }
            ],
            u"owsContext": {
                u"offering": {u"code": u"anyCode", u"content": {u"href": u"anyRef"}}
            },
        }
        return data

    def to_opensearch(self, unique_aoi, unique_toi, wps_inputs=False):
        # type: (bool, bool, bool) -> List[Dict]
        """
        Args:
            unique_aoi:
            unique_toi:
            wps_inputs:
        """
        if not self.eoimage_inputs:
            return self.other_inputs

        eoimage_names = [get_any_id(i) for i in self.eoimage_inputs]
        allowed_collections = [
            self.get_allowed_collections(i) for i in self.eoimage_inputs
        ]

        toi = []
        aoi = []
        collections = []

        unbounded_toi = not unique_toi
        toi_id = u"" if unique_toi else u"_{id}"
        toi.append(
            self.make_toi(u"startDate{}".format(toi_id), unbounded_toi, start_date=True)
        )
        toi.append(
            self.make_toi(u"endDate{}".format(toi_id), unbounded_toi, start_date=False)
        )

        unbounded_aoi = not unique_aoi
        aoi.append(self.make_aoi(u"aoi", unbounded=unbounded_aoi))

        for name, allowed_col in zip(eoimage_names, allowed_collections):
            collections.append(self.make_collection(name, allowed_col))

        new_inputs = toi + aoi + collections
        if wps_inputs:
            new_inputs = [self.convert_to_wps_input(i) for i in new_inputs]
        return new_inputs + self.other_inputs

    @staticmethod
    def convert_to_wps_input(input_):
        """
        Args:
            input_:
        """
        replace = {
            u"id": u"identifier",
            u"minOccurs": u"min_occurs",
            u"maxOccurs": u"max_occurs",
        }
        remove = [
            u"formats",
            u"LiteralDataDomain",
            u"additionalParameters",
            u"owsContext",
        ]
        add = {u"type": u"literal", u"data_type": u"string"}
        for k, v in replace.items():
            if k in input_:
                input_[v] = input_.pop(k)
        for r in remove:
            input_.pop(r, None)
        for k, v in add.items():
            input_[k] = v

        return input_


def get_eoimages_inputs_from_payload(payload):
    """
    Args:
        payload:
    """
    inputs = payload["processDescription"]["process"].get("inputs", {})
    return list(filter(EOImageDescribeProcessHandler.is_eoimage_input, inputs))


def get_eoimages_ids_from_payload(payload):
    """
    Args:
        payload:
    """
    return [get_any_id(i) for i in get_eoimages_inputs_from_payload(payload)]


def replace_inputs_eoimage_files_to_query(inputs, payload, wps_inputs=False):
    # type: (List[Dict], Dict, bool) -> List[Dict]
    """Replace EOImage inputs (additionalParameter -> EOImage -> true) with
    OpenSearch query parameters

    Args:
        inputs:
        payload:
        wps_inputs:
    """

    # add "additionalParameters" property from the payload
    process = payload["processDescription"]["process"]
    payload_inputs = {get_any_id(i): i for i in process.get("inputs", {})}
    for i in inputs:
        try:
            ap = payload_inputs[get_any_id(i)]["additionalParameters"]
            i["additionalParameters"] = ap
        except:
            pass

    additional_parameters = get_additional_parameters(process)

    unique_toi, unique_aoi = True, True  # by default
    if additional_parameters:
        additional_parameters_upper = [
            [p[0].upper(), ",".join([c.upper() for c in p[1]])]
            for p in additional_parameters
        ]
        unique_toi = ["UNIQUETOI", "TRUE"] in additional_parameters_upper
        unique_aoi = ["UNIQUEAOI", "TRUE"] in additional_parameters_upper
    handler = EOImageDescribeProcessHandler(inputs=inputs)
    inputs_converted = handler.to_opensearch(
        unique_aoi=unique_aoi, unique_toi=unique_toi, wps_inputs=wps_inputs
    )
    return inputs_converted
