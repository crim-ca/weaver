import logging
import re
from collections import deque
from copy import deepcopy
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlparse

import shapely.wkt
from pyramid.httpexceptions import HTTPOk
from pyramid.settings import asbool

from weaver import xml_util
from weaver.formats import ContentType
from weaver.processes.constants import WPS_LITERAL, OpenSearchField
from weaver.processes.convert import normalize_ordered_io
from weaver.processes.sources import fetch_data_sources
from weaver.processes.utils import get_process_information
from weaver.utils import get_any_id, request_extra

if TYPE_CHECKING:
    from typing import Deque, Dict, Iterable, List, Optional, Tuple

    from weaver.processes.convert import WPS_Input_Type, JSON_IO_Type
    from weaver.typedefs import AnySettingsContainer, DataSourceOpenSearch, JSON

LOGGER = logging.getLogger("PACKAGE")


def alter_payload_after_query(payload):
    # type: (JSON) -> JSON
    """
    When redeploying the package on :term:`ADES`, strip out any :term:`EOImage` parameter.
    """
    new_payload = deepcopy(payload)
    proc_desc = get_process_information(new_payload)
    inputs = proc_desc["inputs"]
    for input_ in inputs:
        if EOImageDescribeProcessHandler.is_eoimage_input(input_):
            del input_["additionalParameters"]
    return new_payload


WKT_BBOX_BOUNDS = re.compile(
    r"(?P<x1>(\-?\d+(\.\d+)?)),"
    r"(?P<y1>(\-?\d+(\.\d+)?)),"
    r"(?P<x2>(\-?\d+(\.\d+)?)),"
    r"(?P<y2>(\-?\d+(\.\d+)?))"
)


def load_wkt_bbox_bounds(wkt):
    # type: (str) -> str
    bounds = re.match(WKT_BBOX_BOUNDS, wkt)
    if bounds:
        return ",".join(map(str, map(float, wkt.split(","))))
    bounds = shapely.wkt.loads(wkt).bounds
    bbox_str = ",".join(map(str, bounds))
    return bbox_str


def validate_bbox(bbox):
    # type: (str) -> None
    """
    Validate bounding box formatted as ``x1, y1, x2, y2`` string composed of floating point numbers.
    """
    try:
        if not len(list(map(float, bbox.split(",")))) == 4:
            raise ValueError
    except ValueError:
        raise ValueError(f"Could not parse bbox as a list of 4 floats: {bbox}")


def query_eo_images_from_wps_inputs(wps_inputs,             # type: Dict[str, Deque]
                                    eoimage_source_info,    # type: Dict[str, DataSourceOpenSearch]
                                    accept_mime_types,      # type: Dict[str, List[str]]
                                    settings=None,          # type: Optional[AnySettingsContainer]
                                    ):                      # type: (...) -> Dict[str, Deque[WPS_Input_Type]]
    """
    Query `OpenSearch` using parameters in inputs and return file links.

    :param wps_inputs: inputs containing info to query
    :param eoimage_source_info: data source info of eoimages
    :param accept_mime_types: dict of list of accepted mime types, ordered by preference
    :param settings: application settings to retrieve request options as necessary.
    """
    new_inputs = {}

    def get_input_data(ids_to_get):
        # type: (Iterable[str]) -> str
        """
        Check that specified input IDs contain submitted data.

        :raises ValueError: when no input by ID can be found with provided data.
        """
        for id_ in ids_to_get:
            try:
                return wps_inputs[id_][0].data
            except KeyError:
                pass
        ids_choices = " or ".join(ids_to_get)
        raise ValueError(f"Missing input identifier: {ids_choices}")

    def is_eoimage_parameter(param):
        # type: (str) -> bool
        """
        Return ``True`` if the name of this parameter is a query parameter of an ``EOImage``.
        """
        parameters = [
            OpenSearchField.AOI,
            OpenSearchField.START_DATE,
            OpenSearchField.END_DATE
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

                aoi_ids = make_param_id(OpenSearchField.AOI, input_id), OpenSearchField.AOI
                startdate_ids = (make_param_id(OpenSearchField.START_DATE, input_id), OpenSearchField.START_DATE)
                enddate_ids = make_param_id(OpenSearchField.END_DATE, input_id), OpenSearchField.END_DATE

                bbox_str = get_input_data(aoi_ids)
                validate_bbox(load_wkt_bbox_bounds(bbox_str))
                startdate = get_input_data(startdate_ids)
                enddate = get_input_data(enddate_ids)

                params = {"startDate": startdate,
                          "endDate": enddate,
                          "bbox": bbox_str,
                          "maximumRecords": max_occurs}
                osdd_url = eoimage_source_info[input_id]["osdd_url"]
                accept_schemes = eoimage_source_info[input_id]["accept_schemes"]
                mime_types = accept_mime_types[input_id]
                osq = OpenSearchQuery(collection_identifier=collection_id, osdd_url=osdd_url, settings=settings)
                for link in osq.query_datasets(params,
                                               accept_schemes=accept_schemes,
                                               accept_mime_types=mime_types):
                    new_input = deepcopy(queue[0])
                    new_input.data = replace_with_opensearch_scheme(link)
                    eoimages_queue.append(new_input)
                    if len(eoimages_queue) >= max_occurs:
                        break
                if len(eoimages_queue) < queue[0].min_occurs:
                    allowed_mime_types = ", ".join(mime_types)
                    raise ValueError(
                        f"Could not find enough images [{len(eoimages_queue)}/{queue[0].min_occurs}] "
                        f"matching accepted mimetype [{allowed_mime_types}]"
                    )
                new_inputs[input_id] = eoimages_queue

    return new_inputs


def replace_with_opensearch_scheme(link):
    # type: (str) -> str
    """
    Replaces ``file://`` scheme by ``opensearch://`` scheme.
    """
    scheme = urlparse(link).scheme
    if scheme == "file":
        link_without_scheme = link[link.find(":"):]
        return OpenSearchField.LOCAL_FILE_SCHEME + link_without_scheme
    return link


class OpenSearchQuery(object):
    DEFAULT_MAX_QUERY_RESULTS = 5  # usually the default at the OpenSearch server too

    def __init__(
        self,
        collection_identifier,                      # type: str
        osdd_url,                                   # type: str
        catalog_search_field="parentIdentifier",    # type: str
        settings=None,                              # type: Optional[AnySettingsContainer]
    ):                                              # type: (...) -> None
        """
        Container to handle `OpenSearch` queries.

        :param collection_identifier: Collection ID to query
        :param osdd_url: Global OSDD url for `OpenSearch` queries.
        :param catalog_search_field: Name of the field for the collection identifier.
        :param settings: application settings to retrieve request options as necessary.
        """
        self.settings = settings
        self.collection_identifier = collection_identifier
        self.osdd_url = osdd_url
        self.params = {
            catalog_search_field: collection_identifier,
            "httpAccept": "application/geo+json",
        }
        # validate inputs
        if any(c in "/?" for c in collection_identifier):
            raise ValueError(f"Invalid collection identifier: {collection_identifier}")

    def get_template_url(self):
        # type: () -> str
        resp = request_extra("get", self.osdd_url, params=self.params, settings=self.settings)
        resp.raise_for_status()

        data = xml_util.fromstring(resp.content)
        xpath = "//*[local-name() = 'Url'][@rel='results']"
        url = data.xpath(xpath)[0]  # type: xml_util.XML
        return url.attrib["template"]

    def _prepare_query_url(self, template_url, params):
        # type: (str, Dict) -> Tuple[str, JSON]
        """
        Prepare the URL for the `OpenSearch` query.

        :param template_url: url containing query parameters.
        :param params: parameters to insert in formatted URL.
        """
        base_url, query = template_url.split("?", 1)

        query_params = {}
        template_parameters = parse_qsl(query)

        allowed_names = {p[0] for p in template_parameters}
        for key, value in template_parameters:
            if "{" in value and "}" in value:
                pass
            else:  # default value
                query_params[key] = value

        for key, value in params.items():
            if key not in allowed_names:
                raise ValueError(f"Key '{key}' is not an allowed query parameter.")
            query_params[key] = value

        if "maximumRecords" not in query_params:
            query_params["maximumRecords"] = self.DEFAULT_MAX_QUERY_RESULTS

        return base_url, query_params

    def _fetch_datatsets_from_alternates_links(self, alternate_links):
        # Try loading from atom alternate link
        for link in alternate_links:
            if link["type"] == "application/atom+xml":
                resp = request_extra("get", link["href"], settings=self.settings)
                resp.raise_for_status()

                data = xml_util.fromstring(resp.content)
                xpath = "//*[local-name() = 'entry']/*[local-name() = 'link']"
                links = data.xpath(xpath)  # type: List[xml_util.XML]
                return [link.attrib for link in links]
        return []

    def _query_features_paginated(self, params):
        # type: (JSON) -> Iterable[JSON, str]
        """
        Iterates over paginated results until all features are retrieved.

        :param params: query parameters
        """
        start_index = 1
        maximum_records = params.get("maximumRecords")
        template_url = self.get_template_url()
        base_url, query_params = self._prepare_query_url(template_url, params)
        while True:
            query_params["startRecord"] = start_index
            response = request_extra("get", base_url, params=query_params,
                                     intervals=list(range(1, 5)), allowed_codes=[HTTPOk.code],
                                     settings=self.settings)
            if response.status_code != 200:
                break
            json_body = response.json()
            features = json_body.get("features", [])
            for feature in features:
                yield feature, response.url
            n_received_features = len(features)
            n_received_so_far = start_index + n_received_features - 1  # index starts at 1
            total_results = json_body["totalResults"]
            if not n_received_features:
                break
            if n_received_so_far >= total_results:
                break
            if maximum_records and n_received_so_far >= maximum_records:
                break
            start_index += n_received_features

    def query_datasets(self, params, accept_schemes, accept_mime_types):
        # type: (JSON, List[str], List[str]) -> Iterable[str]
        """
        Query the specified datasets.

        Loop on every `OpenSearch` result feature and yield URL matching required mime-type and scheme.
        Log a warning if a feature cannot yield a valid URL (either no compatible mime-type or scheme)

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
                LOGGER.exception("Badly formatted json at: [%s]", url)
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
                # Do not raise an error right now, just loop until we reach the number of inputs we want
                # Raise only if that number isn't reach
                LOGGER.warning("Could not match any accepted mimetype [%s] to received mimetype [%s] using params %s",
                               ", ".join(accept_mime_types), ", ".join(data_links_mime_types), params)


def get_additional_parameters(input_data):
    # type: (JSON) -> List[Tuple[str, str]]
    """
    Retrieve the values from the ``additionalParameters`` of the input.

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
        # type: (List[JSON_IO_Type]) -> None
        self.eoimage_inputs = list(filter(self.is_eoimage_input, inputs))
        self.other_inputs = list(filter(lambda i: self.is_eoimage_input(i) is False, inputs))

    @staticmethod
    def is_eoimage_input(input_data):
        # type: (JSON) -> bool
        for name, value in get_additional_parameters(input_data):
            if name.upper() == "EOIMAGE" and value and len(value) and asbool(value[0]):
                return True
        return False

    @staticmethod
    def get_allowed_collections(input_data):
        # type: (JSON) -> List[str]
        for name, value in get_additional_parameters(input_data):
            if name.upper() == "ALLOWEDCOLLECTIONS":
                return value.split(",")
        return []

    @staticmethod
    def make_aoi(id_):
        # type: (str) -> JSON
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
    def make_collection(identifier, allowed_values):  # noqa: W0613
        # type: (str, List[str]) -> JSON
        description = u"Collection of the data."
        data = {
            u"id": str(identifier),
            u"title": description,
            u"abstract": description,
            u"formats": [{u"mimeType": ContentType.TEXT_PLAIN, u"default": True}],
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
        # type: (str, bool) -> JSON
        """
        Generate the Time-Of-Interest definition.

        :param id_: ID of the input.
        :param start_date:  (Default value = True)
        """
        date = OpenSearchField.START_DATE if start_date else OpenSearchField.END_DATE
        search_field = f"{date[0].lower()}{date[1:]}"
        data = {
            u"id": id_,
            u"title": u"Time of Interest",
            u"abstract": u"Time of Interest (defined as Start date - End date)",
            u"formats": [{u"mimeType": ContentType.TEXT_PLAIN, u"default": True}],
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
        # type: (bool, bool) -> List[JSON]
        """
        Convert the inputs with `OpenSearch` request parameters considering Area-Of-Interest and Time-Of-Interest.

        :param unique_aoi: indicate if a single/global AOI must be applied or individual ones for each input.
        :param unique_toi: indicate if a single/global TOI must be applied or individual ones for each input.
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
            toi.append(self.make_toi(OpenSearchField.START_DATE, start_date=True))
            toi.append(self.make_toi(OpenSearchField.END_DATE, start_date=False))
        else:
            for name in eoimage_names:
                toi.append(
                    self.make_toi(
                        make_param_id(OpenSearchField.START_DATE, name), start_date=True
                    )
                )
                toi.append(
                    self.make_toi(
                        make_param_id(OpenSearchField.END_DATE, name), start_date=False
                    )
                )

        if unique_aoi:
            aoi.append(self.make_aoi(OpenSearchField.AOI))
        else:
            for name in eoimage_names:
                aoi.append(self.make_aoi(make_param_id(OpenSearchField.AOI, name)))

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
    # type: (JSON) -> List[JSON]
    """
    Extracts only inputs that correspond to an :term:`EOImage` based on provided ``additionalParameters``.
    """
    inputs = payload.get("processDescription", {}).get("process", {}).get("inputs", {})
    inputs = normalize_ordered_io(inputs)
    return list(filter(EOImageDescribeProcessHandler.is_eoimage_input, inputs))


def get_original_collection_id(payload, wps_inputs):
    # type: (JSON, Dict[str, deque[WPS_Input_Type]]) -> Dict[str, deque[WPS_Input_Type]]
    """
    Obtains modified WPS inputs considering mapping to known `OpenSearch` collection IDs.

    When we deploy a `Process` that contains `OpenSearch` parameters, the collection identifier is modified::

        Ex: files -> collection
        Ex: s2 -> collection_s2, probav -> collection_probav

    This function changes the ID in the execute request to the one from the deployed `Process` description.

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
            raise ValueError(f"Missing required input parameter: {execute_id}")
        new_inputs[deploy_id] = new_inputs.pop(execute_id)
    return new_inputs


def get_eo_images_data_sources(payload, wps_inputs):
    # type: (Dict, Dict[str, deque[WPS_Input_Type]]) -> Dict[str, DataSourceOpenSearch]
    """
    Resolve the data source of an ``EOImage`` input reference.

    :param payload: Deploy payload
    :param wps_inputs: Execute inputs
    :returns: Data source of the ``EOImage``.
    """
    inputs = get_eo_images_inputs_from_payload(payload)
    eo_image_identifiers = [get_any_id(i) for i in inputs]
    data_sources = {i: get_data_source(wps_inputs[i][0].data) for i in eo_image_identifiers}
    return data_sources


def get_eo_images_mime_types(payload):
    # type: (JSON) -> Dict[str, List[str]]
    """
    Get the accepted media-types from the deployment payload.

    :param payload: Deploy payload.
    :returns: Accepted media-type.
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
    # type: (JSON, Dict[str, Deque[WPS_Input_Type]]) -> None
    """
    Insert maxOccurs value in wps inputs using the deploy payload.

    :param payload: Deploy payload.
    :param wps_inputs: WPS inputs.
    """
    inputs = get_eo_images_inputs_from_payload(payload)

    for input_ in inputs:
        try:
            wps_inputs[get_any_id(input_)][0].max_occurs = int(input_["maxOccurs"])
        except ValueError:
            pass


def modified_collection_identifiers(eo_image_identifiers):
    # type: (List[str]) -> List[str]
    unique_eoimage = len(eo_image_identifiers) == 1
    new_identifiers = []
    for identifier in eo_image_identifiers:
        new = OpenSearchField.COLLECTION if unique_eoimage else make_param_id(identifier, OpenSearchField.COLLECTION)
        new_identifiers.append(new)
    return new_identifiers


def get_data_source(collection_id):
    # type: (str) -> DataSourceOpenSearch
    """
    Obtain the applicable :term:`Data Source` based on the provided collection identifier.

    .. seealso::
        - :ref:`conf_data_sources`
        - :ref:`opensearch_data_source`
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
        raise ValueError(f"No OSDD URL found in data sources for collection ID '{collection_id}'")


def get_eo_images_ids_from_payload(payload):
    # type: (JSON) -> List[str]
    return [get_any_id(i) for i in get_eo_images_inputs_from_payload(payload)]


def replace_inputs_describe_process(inputs, payload):
    # type: (List[JSON], JSON) -> List[JSON]
    """
    Replace ``EOImage`` inputs (if ``additionalParameter -> EOImage -> true``) with `OpenSearch` query parameters.
    """
    if not isinstance(payload, dict):
        return inputs

    payload_process = payload.get("processDescription", {}).get("process", {})
    process_inputs = payload_process.get("inputs", [])
    process_inputs = normalize_ordered_io(process_inputs)

    # add "additionalParameters" property from the payload
    payload_inputs = {get_any_id(i): i for i in process_inputs}
    for i in inputs:
        try:
            params = payload_inputs[get_any_id(i)]["additionalParameters"]
            i["additionalParameters"] = params
        except Exception:  # noqa: W0703 # nosec: B110
            pass

    additional_parameters = get_additional_parameters(payload_process)

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


def make_param_id(param_name, identifier):
    # type: (str, str) -> str
    """
    Only adds an underscore between the parameters.
    """
    return f"{param_name}_{identifier}"
