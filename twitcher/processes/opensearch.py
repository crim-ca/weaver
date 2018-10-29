import time
from collections import deque
from copy import deepcopy
from itertools import ifilterfalse

from twitcher.processes.sources import fetch_data_sources
from twitcher.utils import get_any_id, get_any_value
from pyramid.settings import asbool

import lxml.etree
import requests
import urlparse
import shapely.wkt

from typing import Iterable, Dict, Tuple, List, Deque
import logging

from twitcher.processes.wps_process import OPENSEARCH_LOCAL_FILE_SCHEME

LOGGER = logging.getLogger("PACKAGE")


def alter_payload_after_query(payload):
    """When redeploying the package on ADES, strip out any EOImage parameter

    :param payload: 

    """
    new_payload = deepcopy(payload)

    for input_ in new_payload["processDescription"]["process"]["inputs"]:
        if EOImageDescribeProcessHandler.is_eoimage_input(input_):
            del input_["additionalParameters"]
    return new_payload


def query_eo_images_from_wps_inputs(wps_inputs, eoimage_source_info):
    # type: (Dict[str, Deque], Dict[str, Dict]) -> Dict[str, Deque]
    """Query OpenSearch using parameters in inputs and return file links.

    eoimage_ids is used to identify if a certain input is an eoimage.

    :param wps_inputs: inputs containing info to query
    :param eoimage_source_info: data source info of eoimages
    """
    new_inputs = deepcopy(wps_inputs)

    def pop_first_input(id_to_pop):
        """

        :param id_to_pop: 

        """
        return new_inputs.pop(id_to_pop)

    eoimages_inputs = [
        input_id for input_id in wps_inputs if input_id in eoimage_source_info
    ]
    if eoimages_inputs:
        eoimages_queue = deque()
        for input_id, queue in wps_inputs.items():
            if input_id in eoimage_source_info:
                new_inputs.pop(input_id)

                wkt = pop_first_input("aoi")[0].data
                bbox_str = load_wkt(wkt)

                params = {
                    "startDate": pop_first_input("startDate")[0].data,
                    "endDate": pop_first_input("endDate")[0].data,
                    "bbox": bbox_str,
                }
                osdd_url = eoimage_source_info[input_id]["osdd_url"]
                accept_schemes = eoimage_source_info[input_id]["accept_schemes"]
                os = OpenSearchQuery(
                    collection_identifier=queue[0].data, osdd_url=osdd_url
                )
                for link in os.query_datasets(params, accept_schemes=accept_schemes):
                    new_input = deepcopy(queue[0])
                    new_input.data = replace_with_opensearch_scheme(link)
                    eoimages_queue.append(new_input)

        eoimage_input_name = eoimages_inputs[0]
        new_inputs[eoimage_input_name] = eoimages_queue
    return new_inputs


def replace_with_opensearch_scheme(link):
    """

    :param link: url to replace scheme

    """
    scheme = urlparse.urlparse(link).scheme
    if scheme == "file":
        link_without_scheme = link[link.find(":") :]
        return "{}{}".format(OPENSEARCH_LOCAL_FILE_SCHEME, link_without_scheme)
    else:
        return link


def load_wkt(wkt):
    """

    :param wkt: to get the bounding box of
    :type wkt: string

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
        :param collection_identifier: Collection ID to query
        :param osdd_url: Global OSDD url for opensearch queries.
        :param catalog_search_field: Name of the field for the collection
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
        """ """
        r = requests.get(self.osdd_url, params=self.params)
        r.raise_for_status()

        et = lxml.etree.fromstring(r.content)
        xpath = "//*[local-name() = 'Url'][@rel='results']"
        url = et.xpath(xpath)[0]  # type: lxml.etree._Element
        return url.attrib["template"]

    def _prepare_query_url(self, template_url, params):
        # type: (str, Dict) -> Tuple[str, Dict]
        """

        :param template_url: url containing query parameters
        :param params: parameters to insert in formated url

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
                raise ValueError(
                    "{key} is not an allowed query parameter".format(key=key)
                )
            query_params[key] = value

        query_params["maximumRecords"] = self.MAX_QUERY_RESULTS

        return base_url, query_params

    def requests_get_retry(self, *args, **kwargs):
        """Retry a requests.get call

        :param *args: passed to requests.get
        :param **kwargs: passed to requests.get

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

        :param params: query parameters

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

        :param params: query parameters
        :param accept_schemes: only return links of this scheme

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

    :param input_data: Dict containing or not the "additionalParameters" key
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
        self.eoimage_inputs = list(filter(self.is_eoimage_input, inputs))
        self.other_inputs = list(ifilterfalse(self.is_eoimage_input, inputs))

    @staticmethod
    def is_eoimage_input(input_data):
        # type: (Dict) -> bool
        for name, value in get_additional_parameters(input_data):
            if name.upper() == "EOIMAGE" and value and len(value) and asbool(value[0]):
                return True
        return False

    @staticmethod
    def get_allowed_collections(input_data):
        # type: (Dict) -> List
        for name, value in get_additional_parameters(input_data):
            if name.upper() == "ALLOWEDCOLLECTIONS":
                return value.split(",")
        return []

    @staticmethod
    def make_aoi(id_):
        data = {
            u"id": id_,
            u"title": u"Area of Interest",
            u"abstract": u"Area of Interest (Bounding Box)",
            u"formats": [{u"mimeType": u"OGC-WKT", u"default": True}],
            u"minOccurs": 1,
            u"maxOccurs": 1,
        }
        return data

    @staticmethod
    def make_collection(image_format, allowed_values):
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
    def make_toi(id_, start_date=True):
        """

        :param id_:
        :param start_date:  (Default value = True)

        """
        date = u"startDate" if start_date else u"endDate"
        data = {
            u"id": id_,
            u"title": u"Time of Interest",
            u"abstract": u"Time of Interest (defined as Start date - End date)",
            u"formats": [{u"mimeType": u"text/plain", u"default": True}],
            u"minOccurs": 1,
            u"maxOccurs": 1,
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

    def to_opensearch(self, unique_aoi, unique_toi, to_wps_inputs=False):
        # type: (bool, bool, bool) -> List[Dict]
        """

        :param unique_aoi:
        :param unique_toi:
        :param to_wps_inputs:  (Default value = False)

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

        if unique_toi:
            toi.append(self.make_toi(u"startDate", start_date=True))
            toi.append(self.make_toi(u"endDate", start_date=False))
        else:
            for name in eoimage_names:
                toi.append(self.make_toi(u"startDate_{}".format(name), start_date=True))
                toi.append(self.make_toi(u"endDate_{}".format(name), start_date=False))

        if unique_aoi:
            aoi.append(self.make_aoi(u"aoi"))
        else:
            for name in eoimage_names:
                aoi.append(self.make_aoi(u"aoi_{}".format(name)))

        for name, allowed_col in zip(eoimage_names, allowed_collections):
            collections.append(self.make_collection(name, allowed_col))

        new_inputs = toi + aoi + collections
        if to_wps_inputs:
            new_inputs = [self.convert_to_wps_input(i) for i in new_inputs]
        return new_inputs + self.other_inputs

    @staticmethod
    def convert_to_wps_input(input_):
        """

        :param input_:

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


def get_eo_images_inputs_from_payload(payload):
    """

    :param payload: 

    """
    inputs = payload["processDescription"]["process"].get("inputs", {})
    return list(filter(EOImageDescribeProcessHandler.is_eoimage_input, inputs))


def get_eo_images_data_sources(payload):
    # type: (Dict) -> Dict[str, Dict]
    """

    :param payload:

    """
    inputs = get_eo_images_inputs_from_payload(payload)
    id_with_collection = {get_any_id(i): get_any_value(i) for i in inputs}
    return {k: get_data_source(id_) for k, id_ in id_with_collection.items()}


def get_data_source(collection_id):
    """

    :param collection_id: 

    """
    data_sources = fetch_data_sources()
    for source_data in data_sources.values():
        try:
            if source_data["collection_id"] == collection_id:
                return source_data
        except KeyError:
            pass
    # specific collection id not found, try to return the default one
    try:
        return data_sources["opensearchdefault"]
    except KeyError:
        message = "No osdd url found in data sources for collection id:" + collection_id
        raise ValueError(message)


def get_eo_images_ids_from_payload(payload):
    """

    :param payload: 

    """
    return [get_any_id(i) for i in get_eo_images_inputs_from_payload(payload)]


def replace_inputs_eoimage_files_to_query(inputs, payload, wps_inputs=False):
    # type: (List[Dict], Dict, bool) -> List[Dict]
    """
    Replace EOImage inputs (additionalParameter -> EOImage -> true) with
    OpenSearch query parameters

    :param inputs:
    :param payload:
    :param wps_inputs:
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
        unique_aoi=unique_aoi, unique_toi=unique_toi, to_wps_inputs=wps_inputs
    )
    return inputs_converted
