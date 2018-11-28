from collections import deque
from copy import deepcopy
from itertools import ifilterfalse
from pyramid.httpexceptions import HTTPGatewayTimeout, HTTPOk
from pyramid.settings import asbool
from six.moves.urllib.parse import urlparse, parse_qsl
from typing import Iterable, Dict, Tuple, List, Deque, AnyStr
from twitcher.processes.sources import fetch_data_sources
from twitcher.processes.constants import WPS_LITERAL
from twitcher.utils import get_any_id
from twitcher.processes.wps_process import OPENSEARCH_LOCAL_FILE_SCHEME
from twitcher.processes.constants import START_DATE, END_DATE, AOI, COLLECTION
import lxml.etree
import requests
import logging
import time

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


def validate_bbox(bbox):
    # u"100.0, 15.0, 104.0, 19.0"
    try:
        if not len(list(map(float, bbox.split(",")))) == 4:
            raise ValueError
    except ValueError:
        raise ValueError("Could not parse bbox as a list of 4 floats: {}".format(bbox))


def query_eo_images_from_wps_inputs(wps_inputs, eoimage_source_info, accept_mime_types):
    # type: (Dict[str, Deque], Dict[str, Dict], Dict[str, List[str]]) -> Dict[str, Deque]
    """Query OpenSearch using parameters in inputs and return file links.

    eoimage_ids is used to identify if a certain input is an eoimage.

    :param wps_inputs: inputs containing info to query
    :param eoimage_source_info: data source info of eoimages
    :param accept_mime_types: dict of list of accepted mime types, ordered by preference
    """
    new_inputs = {}

    def get_input_data(ids_to_get):
        # type: (Iterable[str]) -> str
        """

        :param ids_to_get: list of elements to check

        """
        for id_ in ids_to_get:
            try:
                return wps_inputs[id_][0].data
            except KeyError:
                pass
        else:
            raise ValueError(
                "Missing input identifier: {}".format(" or ".join(ids_to_get))
            )

    def is_eoimage_parameter(param):
        # type: (str) -> bool
        """Return True if the name of this parameter is a query parameter"""
        parameters = [
            AOI,
            START_DATE,
            END_DATE
        ]
        return any(param.startswith(p) for p in parameters)

    eoimages_inputs = [
        input_id for input_id in wps_inputs if input_id in eoimage_source_info
    ]
    if eoimages_inputs:
        for input_id, queue in wps_inputs.items():
            eoimages_queue = deque()
            if input_id not in eoimage_source_info:
                if not is_eoimage_parameter(input_id):
                    new_inputs[input_id] = queue
            else:
                collection_id = queue[0].data
                max_occurs = min(queue[0].max_occurs, 100000)

                aoi_ids = _make_specific_identifier(AOI, input_id), AOI
                startdate_ids = (
                    _make_specific_identifier(START_DATE, input_id),
                    START_DATE,
                )
                enddate_ids = _make_specific_identifier(END_DATE, input_id), END_DATE

                bbox_str = get_input_data(aoi_ids)
                validate_bbox(bbox_str)
                startdate = get_input_data(startdate_ids)
                enddate = get_input_data(enddate_ids)

                params = {"startDate": startdate,
                          "endDate": enddate,
                          "bbox": bbox_str,
                          "maximumRecords": max_occurs}
                osdd_url = eoimage_source_info[input_id]["osdd_url"]
                accept_schemes = eoimage_source_info[input_id]["accept_schemes"]
                mime_types = accept_mime_types[input_id]
                os = OpenSearchQuery(
                    collection_identifier=collection_id, osdd_url=osdd_url
                )
                for link in os.query_datasets(params,
                                              accept_schemes=accept_schemes,
                                              accept_mime_types=mime_types):
                    new_input = deepcopy(queue[0])
                    new_input.data = replace_with_opensearch_scheme(link)
                    eoimages_queue.append(new_input)
                    if len(eoimages_queue) >= max_occurs:
                        break
                if len(eoimages_queue) < queue[0].min_occurs:
                    message = "Could not find enough images ({}/{}) matching accepted mimetype ({})"
                    message = message.format(len(eoimages_queue),
                                             queue[0].min_occurs,
                                             ", ".join(mime_types))
                    raise ValueError(message)
                new_inputs[input_id] = eoimages_queue

    return new_inputs


def replace_with_opensearch_scheme(link):
    """

    :param link: url to replace scheme

    """
    scheme = urlparse(link).scheme
    if scheme == "file":
        link_without_scheme = link[link.find(":"):]
        return "{}{}".format(OPENSEARCH_LOCAL_FILE_SCHEME, link_without_scheme)
    else:
        return link


def load_wkt(wkt):
    """

    :param wkt: to get the bounding box of
    :type wkt: string

    """
    import shapely.wkt
    bounds = shapely.wkt.loads(wkt).bounds
    bbox_str = ",".join(map(str, bounds))
    return bbox_str


class OpenSearchQuery(object):
    DEFAULT_MAX_QUERY_RESULTS = 5  # usually the default at the OpenSearch server too

    def __init__(
        self,
        collection_identifier,                      # type: str
        osdd_url,                                   # type: str
        catalog_search_field="parentIdentifier",    # type: str
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
        # noinspection PyProtectedMember
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
        template_parameters = parse_qsl(query)

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

        if "maximumRecords" not in query_params:
            query_params["maximumRecords"] = self.DEFAULT_MAX_QUERY_RESULTS

        return base_url, query_params

    def _fetch_datatsets_from_alternates_links(self, alternate_links):
        # Try loading from atom alternate link
        for link in alternate_links:
            if link["type"] == "application/atom+xml":
                r = requests.get(link["href"])
                r.raise_for_status()

                et = lxml.etree.fromstring(r.content)
                xpath = "//*[local-name() = 'entry']/*[local-name() = 'link']"

                # noinspection PyProtectedMember
                links = et.xpath(xpath)  # type: lxml.etree._Element
                return [link.attrib for link in links]
        return []

    # noinspection PyMethodMayBeStatic
    def requests_get_retry(self, *args, **kwargs):
        """Retry a requests.get call

        :param args: passed to requests.get
        :param kwargs: passed to requests.get
        """
        response = HTTPGatewayTimeout(detail="Request ran out of retries.")
        retries_in_secs = range(1, 6)  # 1 to 5 secs
        for wait in retries_in_secs:
            response = requests.get(*args, **kwargs)
            if response.status_code == HTTPOk.code:
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
        maximum_records = params.get("maximumRecords")
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
            n_recieved_so_far = start_index + n_received_features - 1  # index starts at 1
            total_results = json_body["totalResults"]
            if not n_received_features:
                break
            if n_recieved_so_far >= total_results:
                break
            if maximum_records and n_recieved_so_far >= maximum_records:
                break
            start_index += n_received_features

    def query_datasets(self, params, accept_schemes, accept_mime_types):
        # type: (Dict, Tuple, List) -> Iterable[AnyStr]
        """
        Loop on every opensearch result feature and yield url mathching required mimetype and scheme.
        Log a warning if a feature cannot yield a valid url (either no compatible mimetype or scheme)

        :param params: query parameters
        :param accept_schemes: only return links of this scheme
        :param accept_mime_types: list of accepted mime types, ordered by preference
        :raise KeyError: If the feature doesn't contain a json data section or an atom alternative link
        """
        if params is None:
            params = {}

        for feature, url in self._query_features_paginated(params):
            try:
                try:
                    data_links = feature["properties"]["links"]["data"]
                except KeyError:
                    # Try loading from atom alternate link
                    data_links = self._fetch_datatsets_from_alternates_links(
                        feature["properties"]["links"]["alternates"])
                data_links_mime_types = [d["type"] for d in data_links]
            except KeyError:
                LOGGER.exception("Badly formatted json at: {}".format(url))
                raise
            for mime_type in accept_mime_types:
                good_links = [data["href"]
                              for data in data_links
                              if data["type"] == mime_type and
                              urlparse(data["href"]).scheme in accept_schemes]
                if good_links:
                    yield good_links[0]
                    break
            else:
                message = "Could not match any accepted mimetype ({}) to received mimetype ({})"
                message = message.format(", ".join(accept_mime_types),
                                         ", ".join(data_links_mime_types))
                # Do not raise an error right now, just loop until we reach the number of inputs we want
                # Raise only if that number isn't reach
                LOGGER.warning(message)


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
            u"minOccurs": u"1",
            u"maxOccurs": u"1",
            u"additionalParameters": [
                {
                    u"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                    u"parameters": [
                        {u"name": u"CatalogSearchField", u"values": [u"bbox"]}
                    ],
                }
            ],
        }
        return data

    @staticmethod
    def make_collection(identifier, allowed_values):
        description = u"Collection of the data."
        data = {
            u"id": u"{}".format(identifier),
            u"title": description,
            u"abstract": description,
            u"formats": [{u"mimeType": u"text/plain", u"default": True}],
            u"minOccurs": u"1",
            u"maxOccurs": u"unbounded",
            u"literalDataDomains": [{u"dataType": {u"name": u"String"}}],
            u"additionalParameters": [
                {
                    u"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                    u"parameters": [
                        {
                            u"name": u"CatalogSearchField",
                            u"values": [u"parentIdentifier"],
                        }
                    ],
                }
            ],
        }
        return data

    @staticmethod
    def make_toi(id_, start_date=True):
        """

        :param id_:
        :param start_date:  (Default value = True)

        """
        date = START_DATE if start_date else END_DATE
        search_field = "{}{}".format(date[0].lower(), date[1:])
        data = {
            u"id": id_,
            u"title": u"Time of Interest",
            u"abstract": u"Time of Interest (defined as Start date - End date)",
            u"formats": [{u"mimeType": u"text/plain", u"default": True}],
            u"minOccurs": u"1",
            u"maxOccurs": u"1",
            u"literalDataDomains": [{u"dataType": {u"name": u"String"}}],
            u"additionalParameters": [
                {
                    u"role": "http://www.opengis.net/eoc/applicationContext/inputMetadata",
                    u"parameters": [
                        {u"name": u"CatalogSearchField", u"values": [search_field]}
                    ],
                }
            ],
        }
        return data

    def to_opensearch(self, unique_aoi, unique_toi):
        # type: (bool, bool) -> List[Dict]
        """

        :param unique_aoi:
        :param unique_toi:

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
            toi.append(self.make_toi(START_DATE, start_date=True))
            toi.append(self.make_toi(END_DATE, start_date=False))
        else:
            for name in eoimage_names:
                toi.append(
                    self.make_toi(
                        _make_specific_identifier(START_DATE, name), start_date=True
                    )
                )
                toi.append(
                    self.make_toi(
                        _make_specific_identifier(END_DATE, name), start_date=False
                    )
                )

        if unique_aoi:
            aoi.append(self.make_aoi(AOI))
        else:
            for name in eoimage_names:
                aoi.append(self.make_aoi(_make_specific_identifier(AOI, name)))

        eoimage_names = modified_collection_identifiers(eoimage_names)
        for name, allowed_col in zip(eoimage_names, allowed_collections):
            collections.append(self.make_collection(name, allowed_col))

        new_inputs = toi + aoi + collections

        # inputs must have the WPS input type
        for i in new_inputs:
            i["type"] = WPS_LITERAL
            i["data_type"] = "string"

        return new_inputs + self.other_inputs


def get_eo_images_inputs_from_payload(payload):
    """

    :param payload:

    """
    inputs = payload["processDescription"]["process"].get("inputs", {})
    return list(filter(EOImageDescribeProcessHandler.is_eoimage_input, inputs))


def get_original_collection_id(payload, wps_inputs):
    # type: (Dict, Dict[str, deque]) -> Dict[str, deque]
    """
    When we deploy a Process that contains OpenSearch parameters, the collection identifier is modified.
    Ex: files -> collection
    Ex: s2 -> collection_s2, probav -> collection_probav
    This function changes the id in the execute request to the one in the deploy description.
    :param payload:
    :param wps_inputs:
    :return:
    """
    new_inputs = deepcopy(wps_inputs)
    inputs = get_eo_images_inputs_from_payload(payload)
    original_ids = [get_any_id(i) for i in inputs]

    correspondence = dict(
        zip(modified_collection_identifiers(original_ids), original_ids)
    )
    for execute_id, deploy_id in correspondence.items():
        if execute_id not in new_inputs:
            raise ValueError("Missing required input parameter: {}".format(execute_id))
        new_inputs[deploy_id] = new_inputs.pop(execute_id)
    return new_inputs


def get_eo_images_data_sources(payload, wps_inputs):
    # type: (Dict, Dict[str, deque]) -> Dict[str, Dict]
    """

    :param payload: Deploy payload
    :param wps_inputs: Execute inputs

    """
    inputs = get_eo_images_inputs_from_payload(payload)
    eo_image_identifiers = [get_any_id(i) for i in inputs]
    data_sources = {i: get_data_source(wps_inputs[i][0].data) for i in eo_image_identifiers}
    return data_sources


def get_eo_images_mime_types(payload):
    # type: (Dict) -> Dict[str, List]
    """
    From the deploy payload, get the accepted mime types.
    :param payload: Deploy payload
    """
    inputs = get_eo_images_inputs_from_payload(payload)

    result = {}
    for input_ in inputs:
        formats_default_first = sorted(input_["formats"],
                                       key=lambda x: x.get("default", False),
                                       reverse=True)
        mimetypes = [f["mimeType"] for f in formats_default_first]
        result[get_any_id(input_)] = mimetypes
    return result


def insert_max_occurs(payload, wps_inputs):
    # type: (Dict, Dict[str, Deque]) -> None
    """
    Insert maxOccurs value in wps inputs using the deploy payload.
    :param payload: Deploy payload
    :param wps_inputs: WPS inputs
    """
    inputs = get_eo_images_inputs_from_payload(payload)

    for input_ in inputs:
        try:
            wps_inputs[get_any_id(input_)][0].max_occurs = int(input_["maxOccurs"])
        except ValueError:
            pass
    return


def modified_collection_identifiers(eo_image_identifiers):
    unique_eoimage = len(eo_image_identifiers) == 1
    new_identifiers = []
    for identifier in eo_image_identifiers:
        new = COLLECTION if unique_eoimage else identifier + "_" + COLLECTION
        new_identifiers.append(new)
    return new_identifiers


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


def replace_inputs_describe_process(inputs, payload):
    # type: (List[Dict], Dict) -> List[Dict]
    """
    Replace EOImage inputs (additionalParameter -> EOImage -> true) with
    OpenSearch query parameters

    :param inputs:
    :param payload:
    """
    if not payload:
        return inputs

    # add "additionalParameters" property from the payload
    process = payload["processDescription"]["process"]
    payload_inputs = {get_any_id(i): i for i in process.get("inputs", {})}
    for i in inputs:
        try:
            ap = payload_inputs[get_any_id(i)]["additionalParameters"]
            i["additionalParameters"] = ap
        # noinspection PyBroadException
        except Exception:
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
        unique_aoi=unique_aoi, unique_toi=unique_toi
    )
    return inputs_converted


def _make_specific_identifier(param_name, identifier):
    """
    Only adds an underscore between the parameters
    :param param_name:
    :param identifier:
    """
    return "{}_{}".format(param_name, identifier)
