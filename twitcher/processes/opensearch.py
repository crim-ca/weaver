from collections import deque
from copy import deepcopy
from itertools import ifilterfalse

import lxml.etree
import requests
import urlparse
import shapely.wkt

from typing import Iterable, Dict, Tuple, List, Deque
import logging

LOGGER = logging.getLogger("PACKAGE")


def query_eo_images_from_wps_inputs(wps_inputs, eoimage_ids):
    # type: (Dict[str, Deque], Iterable) -> Dict[str, Deque]
    """Query OpenSearch using parameters in inputs and return file links.

    eoimage_ids is used to identify if a certain input is an eoimage.
    # todo: handle non unique aoi and toi
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
                os = OpenSearchQuery(osdd_url=queue[0].data)

                for link in os.query_datasets(params):
                    new_input = deepcopy(queue[0])
                    new_input.data = "opensearch_" + link
                    eoimages_queue.append(new_input)

        # todo: we take the first one for now, change to handle non unique aoi and toi
        eoimage_input_name = eoimages_inputs[0]
        new_inputs[eoimage_input_name] = eoimages_queue
    return new_inputs


def query_eo_images_from_inputs(inputs, eoimage_ids):
    # type: (List[Tuple[str, str]], Iterable) -> List[Tuple[str, str]]
    """Query OpenSearch using parameters in inputs and return file links.

    eoimage_ids is used to identify if a certain input is an eoimage.
    # todo: handle non unique aoi and toi
    """

    inputs = deepcopy(inputs)

    def pop_first_input(id_to_pop):
        for i in inputs:
            if i[0] == id_to_pop:
                inputs.remove(i)
                return i[1]

    for i in inputs[:]:
        id_, value = i
        if id_ in eoimage_ids:
            inputs.remove(i)

            bbox_str = load_wkt(pop_first_input("aoi"))

            params = {
                "startDate": pop_first_input("startDate"),
                "endDate": pop_first_input("endDate"),
                "bbox": bbox_str,
            }
            os = OpenSearchQuery(osdd_url=value)

            for link in os.query_datasets(params):
                inputs.append((id_, "opensearch_" + link))
    return inputs


def load_wkt(wkt):
    bounds = shapely.wkt.loads(wkt).bounds
    bbox_str = ",".join(map(str, bounds))
    return bbox_str


class OpenSearchQuery(object):
    def __init__(self, osdd_url, osdd_base=None):
        """
        :param osdd_url: url or collection id for the OpenSearch Description Document
        :param osdd_base: base url, defaults to "http://geo.spacebel.be/opensearch/description.xml"  # todo: change
        """
        try:
            osdd_base, query = osdd_url.split("?", 1)
        except ValueError:
            # maybe the collection ID was passed?
            if osdd_base is None:
                osdd_base = "http://geo.spacebel.be/opensearch/description.xml"
            query = "parentIdentifier=%s" % osdd_url
        self.osdd_url = osdd_base
        self.params = dict(urlparse.parse_qsl(query))

        self.params["httpAccept"] = "application/geo+json"

    def get_template_url(self):
        r = requests.get(self.osdd_url, params=self.params)
        r.raise_for_status()

        et = lxml.etree.fromstring(r.content)
        url = et.xpath("//*[local-name() = 'Url'][@rel='results']")[0]  # type: lxml.etree._Element
        return url.attrib["template"]

    def _prepare_query_url(self, template_url, params):
        # type: (str, Dict) -> Tuple[str, Dict]
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
                raise ValueError("{key} is not an allowed query parameter".format(key=key))
            query_params[key] = value

        return base_url, query_params

    def _query_features_paginated(self, params):
        start_page = 1
        template_url = self.get_template_url()
        base_url, query_params = self._prepare_query_url(template_url, params)
        while True:
            query_params["startPage"] = start_page
            response = requests.get(base_url, params=query_params)
            response.raise_for_status()
            json_body = response.json()
            for feature in json_body["features"]:
                yield feature, response.url
            total_results = json_body["totalResults"]
            items_per_page = json_body["itemsPerPage"]
            start_index = json_body["startIndex"]
            if start_index + items_per_page >= total_results:
                break
            start_page += 1

    def query_datasets(self, params=None):
        # type: (Dict) -> Iterable
        if params is None:
            params = {}

        for feature, url in self._query_features_paginated(params):
            try:
                data_links = [d["href"] for d in feature["properties"]["links"]["data"]]
            except KeyError:
                LOGGER.exception("Badly formatted json at: {}".format(url))
                raise

            file_link = [link for link in data_links if urlparse.urlparse(link).scheme == "file"]
            if not file_link:
                LOGGER.debug("No file:// download link for a feature at: {}".format(url))
            file_link = file_link[0]
            yield file_link


def get_additional_parameters(input_data):
    # type: (Dict) -> List[Tuple[str, str]]
    output = []
    additional_parameters = input_data.get("additionalParameters", [])
    for additional_param in additional_parameters:
        for key, value in additional_param.items():
            if key == "parameters":
                for param in value:
                    name = param.get("name", "")
                    value = param.get("value", "")
                    if name:
                        output.append((name, value))
    return output


class EOImageDescribeProcessHandler(object):
    def __init__(self, inputs):
        # type: (List[Dict]) -> None
        self.eoimage_inputs = list(filter(self.is_oeimage_input, inputs))
        self.other_inputs = list(ifilterfalse(self.is_oeimage_input, inputs))

    @staticmethod
    def is_oeimage_input(input_data):
        # type: (Dict) -> bool
        for name, value in get_additional_parameters(input_data):
            # TODO EOImage value is now a list: Tests should be updated accordingly
            if name.upper() == "EOIMAGE" and value[0].upper() == "TRUE":
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
    def make_aoi(id_, unbounded):
        max_occurs = u"unbounded" if unbounded else 1
        data = {
            u"id": id_,
            u"title": u"Area of Interest",
            u"abstract": u"Area of Interest (Bounding Box)",
            u"formats": [{u"mimeType": u"OGC-WKT", u"default": True}],
            u"minOccurs": 1,
            u"maxOccurs": max_occurs
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
            u"LiteralDataDomain": {u"dataType": u"String",
                                   u"allowedValues": allowed_values},
            u"additionalParameters": [{u"role": u"http://www.opengis.net/eoc/applicationContext/inputMetadata",
                                       u"parameters": [{u"name": u"CatalogSearchField", u"value": u"parentIdentifier"}]
                                       }],
            u"owsContext": {u"offering": {u"code": u"anyCode", u"content": {u"href": u"anyRef"}}}
        }
        return data

    @staticmethod
    def make_toi(id_, unbounded, start_date=True):
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
            u"additionalParameters": [{u"role": u"http://www.opengis.net/eoc/applicationContext/inputMetadata",
                                       u"parameters": [{u"name": u"CatalogSearchField", u"value": date}]}],
            u"owsContext": {u"offering": {u"code": u"anyCode", u"content": {u"href": u"anyRef"}}}
        }
        return data

    def to_opensearch(self, unique_aoi, unique_toi, wps_inputs=False):
        # type: (bool, bool, bool) -> List[Dict]
        if not self.eoimage_inputs:
            return self.other_inputs

        eoimage_names = [i.get('id', i.get('identifier')) for i in self.eoimage_inputs]
        allowed_collections = [self.get_allowed_collections(i) for i in self.eoimage_inputs]

        toi = []
        aoi = []
        collections = []

        unbounded_toi = not unique_toi
        toi_id = u"" if unique_toi else u"_{id}"
        toi.append(self.make_toi(u"startDate{}".format(toi_id), unbounded_toi, start_date=True))
        toi.append(self.make_toi(u"endDate{}".format(toi_id), unbounded_toi, start_date=False))

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
        add = {
            u"type": u"literal",
            u"data_type": u"string",
        }
        for k, v in replace.items():
            if k in input_:
                input_[v] = input_.pop(k)
        for r in remove:
            input_.pop(r, None)
        for k, v in add.items():
            input_[k] = v

        return input_


def get_eoimages_inputs_from_payload(payload):
    inputs = payload["processOffering"]["process"].get("inputs", {})
    return list(filter(EOImageDescribeProcessHandler.is_oeimage_input, inputs))


def get_eoimages_ids_from_payload(payload):
    return [i["identifier"] for i in get_eoimages_inputs_from_payload(payload)]


def replace_inputs_eoimage_files_to_query(inputs, payload, wps_inputs=False):
    # type: (List[Dict], Dict, bool) -> List[Dict]
    """Replace EOImage inputs (additionalParameter -> EOImage -> true) with OpenSearch query parameters"""

    # add "additionalParameters" property from the payload
    process = payload["processOffering"]["process"]
    payload_inputs = {i["identifier"]: i for i in process.get("inputs", {})}
    for i in inputs:
        try:
            i["additionalParameters"] = payload_inputs[i["identifier"]]["additionalParameters"]
        except:
            pass

    additional_parameters = get_additional_parameters(process)

    additional_parameters_upper = [[s.upper() for s in p] for p in additional_parameters]
    unique_toi = ["UNIQUETOI", "TRUE"] in additional_parameters_upper
    unique_aoi = ["UNIQUEAOI", "TRUE"] in additional_parameters_upper
    handler = EOImageDescribeProcessHandler(inputs=inputs)
    inputs_converted = handler.to_opensearch(unique_aoi=unique_aoi, unique_toi=unique_toi, wps_inputs=wps_inputs)
    return inputs_converted
