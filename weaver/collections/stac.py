"""
Definitions related to :term:`STAC` representation of :term:`Job` results as a static *Collection Output*.

The generated documents are written next to the :term:`Job` outputs and :term:`Provenance` directories as::

    {WPS_OUTPUT_DIR}[/{CONTEXT}]/{JOB_UUID}-collection/collection.json
    {WPS_OUTPUT_DIR}[/{CONTEXT}]/{JOB_UUID}-collection/items/index.json
    {WPS_OUTPUT_DIR}[/{CONTEXT}]/{JOB_UUID}-collection/items/{itemID}.json

The ``items`` sub-directory mimics the ``/collections/{collectionID}/items`` and
``/collections/{collectionID}/items/{itemID}`` endpoints of the :term:`STAC` API.

.. seealso::
    - https://github.com/crim-ca/weaver/issues/683 (Collection Output)
    - https://github.com/crim-ca/weaver/issues/103 (STAC metadata)
    - https://github.com/crim-ca/weaver/issues/910 (``file:checksum`` and ``file:byte_order``)
    - https://github.com/stac-extensions/processing
    - https://github.com/stac-extensions/application
    - https://github.com/stac-extensions/file
"""
import json
import logging
import os
import re
import shutil
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from typing import TYPE_CHECKING
from urllib.parse import quote, urlparse

from dateutil.parser import isoparse
from pyramid.settings import asbool

from weaver import ogc_definitions as ogc_def
from weaver.__meta__ import __source_repository__, __title__, __version__
from weaver.collections.utils import collection_api_url, collection_enabled
from weaver.execute import ExecuteCollectionFormat
from weaver.formats import ContentType, clean_media_type_format, get_content_type
from weaver.processes.constants import JobInputsOutputsSchema
from weaver.processes.convert import convert_input_values_schema, get_field
from weaver.provenance import ProvenanceFormat
from weaver.utils import (
    compute_file_checksum,
    get_any_id,
    get_any_value,
    get_path_kvp,
    get_settings,
    get_weaver_url,
    localize_datetime,
    now,
    request_extra
)
from weaver.wps.utils import get_wps_output_dir, get_wps_output_url, map_wps_output_location

try:
    import rasterio
    from rasterio.warp import transform_bounds
except ImportError:  # pragma: no cover
    rasterio = None
    transform_bounds = None

if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional, Tuple

    from weaver.datatype import Job, Process
    from weaver.typedefs import URL, AnySettingsContainer, CWL, ExecutionResults, JSON, Link, Path

LOGGER = logging.getLogger(__name__)

STAC_VERSION = "1.1.0"
STAC_SCHEMAS_URL = f"https://schemas.stacspec.org/v{STAC_VERSION}"
STAC_COLLECTION_SCHEMA_URL = f"{STAC_SCHEMAS_URL}/collection-spec/json-schema/collection.json"
STAC_ITEM_SCHEMA_URL = f"{STAC_SCHEMAS_URL}/item-spec/json-schema/item.json"
STAC_COLLECTION_PROFILES = ["stac", ExecuteCollectionFormat.STAC, STAC_COLLECTION_SCHEMA_URL]
STAC_API_DATA_ACCESS = [
    "https://api.stacspec.org/v1.0.0/collections",
    "https://api.stacspec.org/v1.0.0/ogcapi-features",
]
STAC_EXT_PROCESSING = "https://stac-extensions.github.io/processing/v1.2.0/schema.json"
STAC_EXT_APPLICATION = "https://stac-extensions.github.io/application/v0.1.0/schema.json"
STAC_EXT_FILE = "https://stac-extensions.github.io/file/v2.1.0/schema.json"

STAC_COLLECTION_SUFFIX = "-collection"
STAC_COLLECTION_FILE = "collection.json"
STAC_ITEMS_DIR = "items"
STAC_ITEMS_FILE = f"{STAC_ITEMS_DIR}/index.json"
STAC_LICENSE = "other"
STAC_API_MARKER = ".stac-api"
STAC_PROCESSING_LEVEL = "L4"
STAC_MAX_PARSE_SIZE = 10 * 1024 * 1024
STAC_WORLD_BBOX = [-180.0, -90.0, 180.0, 90.0]

PROV_REL = "https://www.w3.org/ns/prov"
ISO_DATETIME_REGEX = re.compile(
    r"^\d{4}-\d{2}-\d{2}([Tt ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([Zz]|[+-]\d{2}:?\d{2})?)?$"
)
FILE_LOCAL_PATH_REGEX = re.compile(r"^[^\r\n\t\\:'\"/]+(/[^\r\n\t\\:'\"/]+)*/?$")


class AmbiguousCollectionItems(ValueError):
    """
    Indicates that geo-like output arrays cannot be unambiguously aligned into STAC Items.
    """


def get_collection_dir_name(job_id):
    # type: (Any) -> str
    """
    Obtains the name of the directory that contains the :term:`STAC` documents of the :term:`Job`.
    """
    return f"{job_id}{STAC_COLLECTION_SUFFIX}"


def get_item_path(item_id):
    # type: (str) -> str
    """
    Obtains the path of a :term:`STAC` Item relative to the collection directory, according to the item ID.

    The path follows the ``items/{itemID}`` convention of the :term:`STAC` API, with an explicit file extension.
    """
    item_key = quote(str(item_id), safe="")
    return f"{STAC_ITEMS_DIR}/{item_key}.json"


def get_collection_api_path(extra_path=None):
    # type: (Optional[str]) -> str
    """
    Converts a path relative to the static collection directory into the equivalent :term:`STAC` API sub-path.
    """
    if not extra_path or extra_path == STAC_COLLECTION_FILE:
        return ""
    if extra_path == STAC_ITEMS_FILE:
        return f"/{STAC_ITEMS_DIR}"
    prefix = f"{STAC_ITEMS_DIR}/"
    if extra_path.startswith(prefix) and extra_path.endswith(".json"):
        return f"/{STAC_ITEMS_DIR}/{extra_path[len(prefix):-len('.json')]}"
    return f"/{extra_path}"


def to_rfc3339(dt):
    # type: (Any) -> Optional[str]
    """
    Converts a datetime into :rfc:`3339` UTC representation as required by :term:`STAC`.
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return localize_datetime(dt, "UTC").strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def get_tiff_byte_order(file_path):
    # type: (Path) -> Optional[str]
    """
    Detects the byte order from the header of a TIFF/GeoTIFF file.

    :returns: ``little-endian``, ``big-endian`` or ``None`` if the file is not a TIFF.
    """
    try:
        with open(file_path, mode="rb") as tif:
            header = tif.read(4)
    except OSError:
        return None
    if header in (b"II*\x00", b"II+\x00"):
        return "little-endian"
    if header in (b"MM\x00*", b"MM\x00+"):
        return "big-endian"
    return None


def get_software_versions(package=None):
    # type: (Optional[CWL]) -> Dict[str, str]
    """
    Obtains the name and version of software involved in the production of the :term:`Job` results.
    """
    software = {__title__.lower(): __version__}
    try:
        software["cwltool"] = importlib_metadata.version("cwltool")
    except importlib_metadata.PackageNotFoundError:  # pragma: no cover
        pass
    docker_image = get_package_docker_image(package)
    if docker_image:
        image, _, tag = docker_image.rpartition(":")
        if not image or "/" in tag:  # no tag, ':' belongs to a registry port
            image, tag = docker_image, "latest"
        software[image] = tag
    return software


def get_package_docker_image(package):
    # type: (Optional[CWL]) -> Optional[str]
    """
    Obtains the first Docker image reference of the :term:`CWL` package if any.
    """
    if not isinstance(package, dict):
        return None
    for field in ["requirements", "hints"]:
        reqs = package.get(field) or {}
        if isinstance(reqs, dict):
            reqs = [dict(req, **{"class": cls}) for cls, req in reqs.items() if isinstance(req, dict)]
        for req in reqs:
            if isinstance(req, dict) and req.get("class") == "DockerRequirement":
                return req.get("dockerPull")
    return None


def get_package_entrypoint(package):
    # type: (Optional[CWL]) -> Optional[str]
    """
    Obtains the base command of the :term:`CWL` package if any.
    """
    if not isinstance(package, dict):
        return None
    command = package.get("baseCommand")
    if isinstance(command, list):
        command = " ".join(str(cmd) for cmd in command)
    return str(command) if command else None


def get_package_source_urls(package):
    # type: (Optional[CWL]) -> List[str]
    """
    Obtains the source code references embedded in the metadata of the :term:`CWL` package if any.
    """
    urls = []  # type: List[str]
    if not isinstance(package, dict):
        return urls
    for key, value in package.items():
        if not isinstance(key, str) or not key.endswith("codeRepository"):
            continue
        for item in value if isinstance(value, list) else [value]:
            url = item.get("id") or item.get("@id") if isinstance(item, dict) else item
            if isinstance(url, str) and url and url not in urls:
                urls.append(url)
    return urls


def make_link(href, rel, title=None, media_type=None, **kwargs):
    # type: (URL, str, Optional[str], Optional[str], **Any) -> Link
    link = {"href": href, "rel": rel}  # type: Link
    if media_type:
        link["type"] = media_type
    if title:
        link["title"] = title
    link.update(kwargs)  # type: ignore
    return link


def is_wgs84(crs):
    # type: (Any) -> bool
    """
    Indicates if the :term:`CRS` reference is absent (assumed default) or one of the known longitude/latitude systems.
    """
    if not crs:
        return True
    if isinstance(crs, dict):
        crs = crs.get("uri") or crs.get("href") or (crs.get("properties") or {}).get("name")
    if not isinstance(crs, str):
        return False
    crs = crs.strip()
    return crs.upper() in [ref.upper() for ref in ogc_def.OGC_DEF_CRS_ANY_EPSG4326]


def validate_bbox(bbox):
    # type: (Any) -> Optional[List[float]]
    """
    Validates and reduces a bounding box to its 2D ``[minx, miny, maxx, maxy]`` longitude/latitude representation.
    """
    if not isinstance(bbox, (list, tuple)) or len(bbox) not in [4, 6]:
        return None
    if not all(isinstance(val, (int, float)) and not isinstance(val, bool) for val in bbox):
        return None
    if len(bbox) == 6:
        bbox = [bbox[0], bbox[1], bbox[3], bbox[4]]
    minx, miny, maxx, maxy = [float(val) for val in bbox]
    if not (-180 <= minx <= 180 and -180 <= maxx <= 180 and -90 <= miny <= 90 and -90 <= maxy <= 90):
        return None
    if miny > maxy:
        return None
    return [minx, miny, maxx, maxy]


def merge_bbox(boxes):
    # type: (List[Optional[List[float]]]) -> Optional[List[float]]
    """
    Obtains the largest bounding box that contains all provided ones.
    """
    boxes = [box for box in boxes if box]
    if not boxes:
        return None
    return [
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    ]


def get_coordinates_bbox(coordinates):
    # type: (Any) -> Optional[List[float]]
    """
    Obtains the bounding box of arbitrarily nested :term:`GeoJSON` coordinates.
    """
    points = []  # type: List[Tuple[float, float]]
    stack = [coordinates]
    while stack:
        item = stack.pop()
        if not isinstance(item, (list, tuple)) or not item:
            continue
        if all(isinstance(val, (int, float)) and not isinstance(val, bool) for val in item):
            if len(item) >= 2:
                points.append((float(item[0]), float(item[1])))
            continue
        stack.extend(item)
    if not points:
        return None
    xs, ys = zip(*points)
    return validate_bbox([min(xs), min(ys), max(xs), max(ys)])


def get_value_bbox(value):
    # type: (Any) -> Optional[List[float]]
    """
    Obtains the bounding box of an inline value, if it is a :term:`GeoJSON` or a bounding box definition.

    Recognized contents are ``bbox`` members (including :term:`OGC` bounding box values with a ``crs``),
    :term:`GeoJSON` geometries, features and collections. Others are ignored.
    """
    if isinstance(value, list):
        return merge_bbox([get_value_bbox(item) for item in value])
    if not isinstance(value, dict):
        return None
    if value.get("value") is not None and isinstance(value["value"], (dict, list)):
        return get_value_bbox(value["value"])
    if value.get("bbox") is not None:
        if not is_wgs84(value.get("crs")):
            return None
        bbox = validate_bbox(value["bbox"])
        if bbox:
            return bbox
    geo_type = value.get("type")
    if geo_type == "FeatureCollection":
        return merge_bbox([get_value_bbox(feat) for feat in value.get("features") or []])
    if geo_type == "Feature":
        return get_value_bbox(value.get("geometry"))
    if geo_type == "GeometryCollection":
        return merge_bbox([get_value_bbox(geom) for geom in value.get("geometries") or []])
    if geo_type in ["Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon"]:
        return get_coordinates_bbox(value.get("coordinates"))
    return None


def load_json_file(file_path, media_type):
    # type: (Path, Optional[str]) -> Any
    """
    Loads the :term:`JSON` contents of a file, if it is of a :term:`JSON`-like type and of reasonable size.
    """
    media_type = clean_media_type_format(media_type, suffix_subtype=True, strip_parameters=True)
    file_type = get_content_type(os.path.splitext(file_path)[-1].lower())
    file_type = clean_media_type_format(file_type, suffix_subtype=True, strip_parameters=True)
    is_json = ContentType.APP_JSON in (media_type, file_type)
    if not is_json or os.path.getsize(file_path) > STAC_MAX_PARSE_SIZE:
        return None
    try:
        with open(file_path, mode="r", encoding="utf-8") as json_file:
            return json.load(json_file)
    except (OSError, ValueError):
        return None


def get_raster_bbox(file_path):
    # type: (Path) -> Optional[List[float]]
    """
    Obtains the bounding box of a georeferenced raster (e.g.: GeoTIFF) as longitude/latitude, if supported.
    """
    if rasterio is None:  # pragma: no cover
        return None
    try:
        with rasterio.open(file_path) as dataset:
            if dataset.crs is None:
                return None
            bounds = dataset.bounds
            if not is_wgs84(dataset.crs.to_string()):
                bounds = transform_bounds(dataset.crs, ogc_def.OGC_DEF_CRS_EPSG4326_SHORT, *bounds)
            return validate_bbox(list(bounds))
    except Exception:  # noqa: W0703  # many format-specific errors, any failure simply means no spatial extent
        return None


def get_file_bbox(file_path, media_type=None):
    # type: (Path, Optional[str]) -> Optional[List[float]]
    """
    Obtains the bounding box of a file from its contents, if the format is a known source of spatial extents.
    """
    content = load_json_file(file_path, media_type)
    if content is not None:
        return get_value_bbox(content)
    media_type = clean_media_type_format(media_type, strip_parameters=True)
    file_type = get_content_type(os.path.splitext(file_path)[-1].lower())
    if media_type in ContentType.ANY_TIFF or file_type in ContentType.ANY_TIFF:
        return get_raster_bbox(file_path)
    return None


def parse_datetime(value):
    # type: (str) -> Optional[datetime]
    """
    Parses an :term:`ISO` 8601 date or date-time (as UTC if not specified), or returns ``None`` if not matching.
    """
    value = value.strip()
    if not ISO_DATETIME_REGEX.match(value):
        return None
    try:
        dt = isoparse(value.replace(" ", "T", 1))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return localize_datetime(dt, "UTC")


def find_datetimes(value, _depth=0):
    # type: (Any, int) -> List[datetime]
    """
    Finds all :term:`ISO` 8601 date-time values, including bounds of intervals (``start/end``), nested in a value.
    """
    if _depth > 8:
        return []
    found = []  # type: List[datetime]
    if isinstance(value, str):
        parts = value.split("/") if value.count("/") == 1 else [value]
        for part in parts:
            dt = parse_datetime(part) if part and part != ".." else None
            if dt:
                found.append(dt)
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(find_datetimes(item, _depth + 1))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.extend(find_datetimes(item, _depth + 1))
    return found


def get_geojson_geometry(bbox):
    # type: (Optional[List[float]]) -> Optional[JSON]
    """
    Generates the :term:`GeoJSON` ``Point`` or ``Polygon`` geometry that corresponds to a bounding box.
    """
    if not bbox:
        return None
    minx, miny, maxx, maxy = bbox
    if minx == maxx and miny == maxy:
        return {"type": "Point", "coordinates": [minx, miny]}
    return {
        "type": "Polygon",
        "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]],
    }


class JobCollection(object):
    """
    Builder of the :term:`STAC` Collection and Items that represent the results of a :term:`Job`.
    """

    def __init__(self, job, settings, results, process=None):
        # type: (Job, AnySettingsContainer, ExecutionResults, Optional[Process]) -> None
        """
        Initialize the builder.

        :param job: Successful :term:`Job` which generated the results.
        :param settings: Application settings to resolve server endpoints and output locations.
        :param results: Results of the job using the :term:`OGC` mapping representation with resolved ``href`` values.
        :param process: Process definition from which the results were generated, if available.
        """
        self.job = job
        self.settings = get_settings(settings)
        self.results = results
        self.process = process
        self.package = process.package if process is not None else None
        # Delay this dependency to avoid the datatype -> collections -> wps_package import cycle.
        from weaver.processes.wps_package import mask_process_inputs

        inputs = mask_process_inputs(self.package, deepcopy(job.inputs or []))
        self.inputs = convert_input_values_schema(inputs, JobInputsOutputsSchema.OGC)
        self.input_values = [
            (in_id, in_item)
            for in_id, in_val in self.inputs.items()
            for in_item in (in_val if isinstance(in_val, list) else [in_val])
        ]
        self.out_dir = get_wps_output_dir(self.settings)
        self.out_url = get_wps_output_url(self.settings).rstrip("/")
        self.collection_url = job.collection_url(self.settings)
        self.collection_dir = job.collection_path(self.settings)
        self.job_url = job.job_url(self.settings)
        self.process_url = job.process_url(self.settings)
        self.weaver_url = get_weaver_url(self.settings)
        self.prov_enabled = asbool(self.settings.get("weaver.cwl_prov", True))
        self.finished = to_rfc3339(job.finished or now())
        self.started = to_rfc3339(job.started or job.created)
        self.created = to_rfc3339(job.created)
        self.extents = {}  # type: Dict[str, List[Tuple[Optional[List[float]], List[datetime]]]]
        self.reference_datetimes = []  # type: List[datetime]
        self.item_count = 1
        self.geo_output_ids = []  # type: List[str]
        self.collection_assets = {}  # type: Dict[str, JSON]
        self.asset_documents = {}  # type: Dict[str, JSON]

    def item_url(self, item_id):
        # type: (str) -> URL
        return self.job.collection_url(self.settings, get_item_path(item_id))

    def output_definition(self, output_id):
        # type: (str) -> JSON
        """
        Obtains the process description of the output ID if available.
        """
        outputs = self.process.outputs if self.process is not None else None
        for output in outputs or []:
            if isinstance(output, dict) and get_any_id(output) == output_id:
                return output
        return {}

    def result_local_path(self, href):
        # type: (str) -> Optional[Path]
        if not isinstance(href, str):
            return None
        if href.startswith("file://"):
            href = href[7:]
        if href.startswith(self.out_url):
            return map_wps_output_location(href, self.settings, exists=False)
        if href.startswith(self.out_dir):
            return href
        return None

    def get_result_extent(self, result):
        # type: (Any) -> Tuple[Optional[List[float]], List[datetime]]
        """
        Obtains the largest spatial extent and all temporal references that can be found from the values of a result.

        Both inline values and contents of local files of known formats are considered.
        """
        boxes = []  # type: List[Optional[List[float]]]
        times = []  # type: List[datetime]
        for item in result if isinstance(result, list) else [result]:
            if isinstance(item, dict) and "href" in item:
                local = self.result_local_path(item["href"])
                if not local or not os.path.isfile(local):
                    continue
                media_type = self.get_media_type(item)
                boxes.append(get_file_bbox(local, media_type))
                content = load_json_file(local, media_type)
                if content is not None:
                    times.extend(find_datetimes(content))
            else:
                boxes.append(get_value_bbox(item))
                times.extend(find_datetimes(item))
        return merge_bbox(boxes), times

    @staticmethod
    def get_media_type(value):
        # type: (Any) -> Optional[str]
        """
        Obtains a media type from a result or format definition.
        """
        if not isinstance(value, dict):
            return None
        fmt = value.get("format") or {}
        if isinstance(fmt, str):
            return fmt
        value_type = value.get("type")
        if isinstance(value_type, str) and "/" in value_type:
            return value_type
        return (
            get_field(value, "mime_type", search_variations=True, default=None) or
            get_field(fmt, "mime_type", search_variations=True, default=None)
        )

    def output_format(self, output_id, result=None):
        # type: (str, Any) -> JSON
        """
        Resolves the applicable output format from the result or process description.
        """
        if isinstance(result, dict) and isinstance(result.get("format"), dict):
            return result["format"]
        out_def = self.output_definition(output_id)
        fmt = out_def.get("format")
        if isinstance(fmt, dict):
            return fmt
        formats = out_def.get("formats") or []
        for fmt in formats:
            if isinstance(fmt, dict) and fmt.get("default"):
                return fmt
        return formats[0] if formats and isinstance(formats[0], dict) else {}

    def output_media_type(self, output_id, result=None):
        # type: (str, Any) -> Optional[str]
        result_type = self.get_media_type(result)
        if result_type:
            return result_type
        out_def = self.output_definition(output_id)
        out_type = self.get_media_type(out_def)
        if out_type:
            return out_type
        return self.get_media_type(self.output_format(output_id, result))

    def is_geospatial_result(self, output_id, result):
        # type: (str, Any) -> bool
        """
        Identifies outputs whose arrays can determine the spatial itemization of the collection.
        """
        media_type = clean_media_type_format(self.output_media_type(output_id), strip_parameters=True)
        media_type = media_type.lower() if media_type else None
        geo_media_types = {
            *ContentType.ANY_GEOJSON, *ContentType.ANY_NETCDF, *ContentType.ANY_TIFF,
            "image/vnd.stac.geotiff", "application/geopackage+sqlite3",
            "application/vnd.google-earth.kml+xml", "application/vnd.google-earth.kmz",
            "application/gml+xml", "application/vnd.las", "application/vnd.laszip",
        }
        if media_type in geo_media_types:
            return True
        if not isinstance(result, list):
            return False
        for item in result:
            item_type = clean_media_type_format(self.get_media_type(item), strip_parameters=True)
            item_type = item_type.lower() if item_type else None
            href = item.get("href") if isinstance(item, dict) else None
            if item_type in geo_media_types:
                return True
            if isinstance(href, str):
                extension = os.path.splitext(urlparse(href).path)[-1].lower()
                file_type = get_content_type(extension)
                file_type = clean_media_type_format(file_type, strip_parameters=True)
                if file_type in geo_media_types or extension in (
                    ".cog", ".gpkg", ".nc", ".kml", ".kmz", ".gml", ".las"
                ):
                    return True
                if file_type == ContentType.APP_JSON:
                    local = self.result_local_path(href)
                    content = load_json_file(local, item_type) if local and os.path.isfile(local) else None
                    if content is not None and get_value_bbox(content) is not None:
                        return True
            if get_value_bbox(item) is not None:
                return True
        return False

    def resolve_item_count(self):
        # type: () -> None
        """
        Resolves a shared Item count from geo-like output arrays, rejecting ambiguous cardinalities.
        """
        array_lengths = {
            out_id: len(result)
            for out_id, result in self.results.items() if isinstance(result, list)
        }
        geo_lengths = {
            out_id: length for out_id, length in array_lengths.items()
            if self.is_geospatial_result(out_id, self.results[out_id])
        }
        self.geo_output_ids = list(geo_lengths)
        if not geo_lengths:
            self.item_count = 1
            return
        length_matches = {
            length: sum(1 for other_length in array_lengths.values() if other_length == length)
            for length in geo_lengths.values()
        }
        best_match_count = max(length_matches.values())
        best_lengths = [length for length, count in length_matches.items() if count == best_match_count]
        if len(best_lengths) != 1:
            candidates = ", ".join(f"{out_id}={length}" for out_id, length in geo_lengths.items())
            raise AmbiguousCollectionItems(
                "Geo-like output arrays have ambiguous cardinalities and cannot be aligned: "
                f"{candidates}. Provide output arrays with a unique most-common geo-like length."
            )
        self.item_count = best_lengths[0]
        if self.item_count < 1:
            candidates = ", ".join(f"{out_id}={length}" for out_id, length in geo_lengths.items())
            raise AmbiguousCollectionItems(
                f"Geo-like output arrays contain no items: {candidates}."
            )

    def resolve_extents(self):
        # type: () -> None
        """
        Resolves the spatial and temporal references of every result, and those of the :term:`Job` as a whole.

        Datetimes provided by any input or output of the :term:`Job` serve as fallback for results without their own.
        """
        self.resolve_item_count()
        self.extents = {
            out_id: [self.get_result_extent(item) for item in result]
            if isinstance(result, list) else [self.get_result_extent(result)]
            for out_id, result in self.results.items()
        }
        times = [dt for extents in self.extents.values() for _, out_times in extents for dt in out_times]
        for _, in_val in self.input_values:
            times.extend(find_datetimes(in_val))
        self.reference_datetimes = times

    def make_datetime_properties(self, item_index):
        # type: (int) -> JSON
        """
        Generates the :term:`STAC` Item temporal properties from the references found, or the :term:`Job` time.
        """
        times = [
            dt
            for output_id, result in self.results.items()
            if not isinstance(result, list) or len(result) == self.item_count
            for extents in [self.extents[output_id]]
            if item_index < len(extents)
            for dt in extents[item_index][1]
        ] or self.reference_datetimes
        if not times:
            return {"datetime": self.finished}
        start, end = min(times), max(times)
        if start == end:
            return {"datetime": to_rfc3339(start)}
        return {"datetime": None, "start_datetime": to_rfc3339(start), "end_datetime": to_rfc3339(end)}

    def make_processing_properties(self, output_ids=None):
        # type: (Optional[Any]) -> JSON
        """
        Generates the fields of the :term:`STAC` *Processing* extension.
        """
        proc_id = self.job.process
        provider = self.job.service
        lineage = f"Result generated by Job [{self.job.id}] of Process [{proc_id}]"
        if provider:
            lineage += f" from Provider [{provider}]"
        lineage += f" executed on [{self.weaver_url or __title__}]."
        if output_ids:
            output_ids = output_ids if isinstance(output_ids, list) else [output_ids]
            lineage = f"Outputs [{', '.join(str(out_id) for out_id in output_ids)}]. {lineage}"
        props = {
            "processing:lineage": lineage,
            "processing:facility": self.settings.get("weaver.wps_metadata_provider_name") or
            self.weaver_url or __title__,
            "processing:datetime": self.finished,
            "processing:level": STAC_PROCESSING_LEVEL,
            "processing:software": get_software_versions(self.package),
        }  # type: JSON
        version = self.process.version if self.process is not None else None
        if version:
            props["processing:version"] = str(version)
        return props

    def make_processing_parameters(self):
        # type: () -> JSON
        """
        Resolves named execution inputs for the Processing Extension expression parameters.
        """
        parameters = {}  # type: JSON
        for in_id, in_val in self.inputs.items():
            if not in_id:
                continue
            if isinstance(in_val, dict):
                value = get_any_value(in_val, file=False)
                if value is None:
                    href = get_any_value(in_val, file=True, data=False)
                    value = {"href": href} if href else None
            else:
                value = in_val
            if value is None:
                continue
            parameters[in_id] = value
        return parameters

    def make_application_properties(self):
        # type: () -> JSON
        """
        Generates the fields of the :term:`STAC` *Application* extension.
        """
        if not isinstance(self.package, dict):
            return {}
        props = {"application:languages": ["CWL"]}  # type: JSON
        entrypoint = get_package_entrypoint(self.package)
        if entrypoint:
            props["application:entrypoint"] = entrypoint
        return props

    def make_reference_links(self):
        # type: () -> List[Link]
        """
        Generates links to the :term:`Job`, :term:`Process`, server and :term:`Provenance` references.
        """
        job_url = self.job_url
        links = [
            make_link(job_url, "processing-execution", "Job status.", ContentType.APP_JSON),
            make_link(f"{job_url}/results", "https://www.opengis.net/def/rel/ogc/1.0/results",
                      "Job results.", ContentType.APP_JSON),
            make_link(f"{job_url}/outputs", "outputs", "Job outputs with extended metadata.", ContentType.APP_JSON),
            make_link(f"{job_url}/definition", "definition",
                      "Job definition with the submitted inputs and outputs.", ContentType.APP_JSON),
            make_link(f"{job_url}/logs", "https://www.opengis.net/def/rel/ogc/1.0/log",
                      "Job execution logs.", ContentType.APP_JSON),
            make_link(self.process_url, "describedby", "Process description.", ContentType.APP_JSON),
            make_link(self.weaver_url or self.out_url, "application-platform",
                      "Server that executed the process.", ContentType.APP_JSON),
            make_link(__source_repository__, "vcs", "Source code repository of the server application."),
        ]
        if isinstance(self.package, dict):
            package_url = f"{self.process_url}/package"
            links.extend([
                make_link(package_url, "application", "Application Package (CWL) of the process.",
                          ContentType.APP_JSON, **self.make_application_properties()),
                make_link(package_url, "processing-expression", "Processing chain that produced the results.",
                          ContentType.APP_JSON),
            ])
        if self.prov_enabled:
            links.append(
                make_link(f"{job_url}/prov", "processing-expression", "Job provenance.", ContentType.APP_JSON)
            )
            links.extend(
                make_link(get_path_kvp(f"{job_url}/prov", f=fmt), PROV_REL, "Job provenance.",
                          ProvenanceFormat.as_media_type(fmt))
                for fmt in ProvenanceFormat.formats()
            )
        for src_url in get_package_source_urls(self.package):
            links.append(make_link(src_url, "processing-software", "Source code of the application package."))
        for in_id, in_val in self.input_values:
            href = get_any_value(in_val, data=False, file=True) if isinstance(in_val, dict) else None
            if isinstance(href, str) and href:
                link = make_link(href, "derived_from", f"Job input [{in_id}].", id=str(in_id))
                if isinstance(in_val, dict):
                    media_type = self.get_media_type(in_val)
                    if media_type:
                        link["type"] = media_type
                links.append(link)
        return links

    def collection_asset_url(self, path):
        # type: (str) -> URL
        """
        Resolves a public static URL for an asset stored alongside the collection.
        """
        rel_path = os.path.join(os.path.dirname(self.job.result_path()), get_collection_dir_name(self.job.id))
        rel_path = f"{rel_path}/{path}".replace(os.sep, "/")
        return f"{self.out_url}/{quote(rel_path, safe='/')}"

    def make_reference_asset(self, item, title, role, output_id=None):
        # type: (JSON, str, str, Optional[str]) -> JSON
        """
        Generates a referenced asset with the corresponding Processing and File extension metadata.
        """
        href = get_any_value(item, data=False)
        media_type = self.get_media_type(item)
        if not media_type and output_id:
            media_type = self.output_media_type(output_id, item)
        if not media_type and isinstance(href, str):
            media_type = get_content_type(
                os.path.splitext(urlparse(href).path)[-1].lower(), default=ContentType.TEXT_PLAIN
            )
        asset = {
            "href": href,
            "type": media_type or ContentType.APP_JSON,
            "title": title,
            "roles": ["data", role],
        }  # type: JSON
        fmt = self.output_format(output_id, item) if output_id else item.get("format") or {}
        profile = (fmt.get("profile") if isinstance(fmt, dict) else None) or item.get("profile")
        if profile:
            asset["profile"] = profile
        if output_id:
            out_def = self.output_definition(output_id)
            if out_def.get("description"):
                asset["description"] = out_def["description"]
        if output_id:
            asset.update(self.make_processing_properties(output_id))
        local = self.result_local_path(href)
        if local and os.path.isfile(local):
            stat = os.stat(local)
            asset["file:size"] = stat.st_size
            asset["file:checksum"] = compute_file_checksum(local)
            byte_order = get_tiff_byte_order(local)
            if byte_order:
                asset["file:byte_order"] = byte_order
            rel_path = os.path.relpath(local, self.out_dir)
            job_rel = rel_path.split(os.sep, 1)[-1] if rel_path.startswith(str(self.job.id)) else rel_path
            if FILE_LOCAL_PATH_REGEX.match(job_rel):
                asset["file:local_path"] = job_rel
        if item.get("digestMultibase"):
            asset["digestMultibase"] = item["digestMultibase"]
        return asset

    def item_output_value(self, result, item_index):
        # type: (Any, int) -> Any
        """
        Obtains an output value aligned to the Item, or the scalar value shared by all Items.
        """
        if not isinstance(result, list):
            return result
        if len(result) != self.item_count:
            return None
        return result[item_index]

    def make_assets(self, item_index):
        # type: (int) -> Tuple[Dict[str, JSON], JSON]
        """
        Generates the :term:`STAC` Assets and literal values of outputs aligned to an Item.
        """
        assets = {}  # type: Dict[str, JSON]
        values = {}  # type: JSON
        for output_id, result in self.results.items():
            item = self.item_output_value(result, item_index)
            if item is None and isinstance(result, list) and len(result) != self.item_count:
                continue
            if isinstance(item, dict) and "href" not in item and self.is_geospatial_result(output_id, [item]):
                path = f"assets/items/{self.job.id}-{item_index}/{quote(str(output_id), safe='')}.json"
                self.asset_documents[path] = item
                out_def = self.output_definition(output_id)
                asset = {
                    "href": self.collection_asset_url(path),
                    "type": self.output_media_type(output_id, item) or ContentType.APP_GEOJSON,
                    "title": out_def.get("title") or output_id,
                    "roles": ["data", "processing-output"],
                }  # type: JSON
                fmt = self.output_format(output_id, item)
                profile = fmt.get("profile") if isinstance(fmt, dict) else None
                if profile:
                    asset["profile"] = profile
                asset.update(self.make_processing_properties(output_id))
                assets[quote(str(output_id), safe="")] = asset
                continue
            if not isinstance(item, dict) or "href" not in item:
                data = get_any_value(item) if isinstance(item, dict) else item
                if data is None and isinstance(item, dict):
                    data = item
                values[output_id] = data
                continue
            out_def = self.output_definition(output_id)
            key = quote(str(output_id), safe="")
            assets[key] = self.make_reference_asset(
                item, out_def.get("title") or output_id, "processing-output", output_id
            )
        return assets, values

    def make_collection_assets(self):
        # type: () -> Dict[str, JSON]
        """
        Generates Collection-level assets for execution metadata and output arrays not aligned to Items.
        """
        self.asset_documents = {}
        assets = {}  # type: Dict[str, JSON]
        parameters = self.make_processing_parameters()
        for index, (in_id, in_val) in enumerate(self.input_values):
            href = get_any_value(in_val, file=True, data=False) if isinstance(in_val, dict) else None
            if not isinstance(href, str) or not href:
                continue
            asset = self.make_reference_asset(in_val, f"Input [{in_id}]", "processing-input")
            input_index = index + 1
            key = f"input-{quote(str(in_id), safe='')}"
            if key in assets:
                key = f"{key}-{input_index}"
            assets[key] = asset

        for path, content, title, role in [
            ("assets/results.json", self.results, "Complete job results document", "processing-results"),
            ("assets/parameters.json", parameters, "Job execution parameters", "processing-parameters"),
        ]:
            if content:
                self.asset_documents[path] = content
                assets[os.path.basename(path).split(".", 1)[0]] = {
                    "href": self.collection_asset_url(path),
                    "type": ContentType.APP_JSON,
                    "title": title,
                    "roles": ["data", role],
                }

        for output_id, result in self.results.items():
            if not isinstance(result, list) or len(result) == self.item_count:
                continue
            out_def = self.output_definition(output_id)
            for index, item in enumerate(result):
                key = f"output-{quote(str(output_id), safe='')}-{index}"
                if isinstance(item, dict) and ("href" in item or "reference" in item):
                    assets[key] = self.make_reference_asset(
                        item, out_def.get("title") or output_id, "processing-output", output_id
                    )
                else:
                    path = f"assets/outputs/{quote(str(output_id), safe='')}-{index}.json"
                    value = get_any_value(item) if isinstance(item, dict) else item
                    if value is None and isinstance(item, dict):
                        value = item
                    self.asset_documents[path] = value
                    is_geo_value = self.is_geospatial_result(output_id, [item])
                    media_type = self.output_media_type(output_id, item) if is_geo_value else ContentType.APP_JSON
                    if is_geo_value and not media_type:
                        media_type = ContentType.APP_GEOJSON
                    assets[key] = {
                        "href": self.collection_asset_url(path),
                        "type": media_type,
                        "title": f"{out_def.get('title') or output_id} [{index}]",
                        "roles": ["data", "processing-output"],
                    }
                    fmt = self.output_format(output_id, item)
                    profile = fmt.get("profile") if isinstance(fmt, dict) else None
                    if profile:
                        assets[key]["profile"] = profile
                    assets[key].update(self.make_processing_properties(output_id))
        self.collection_assets = assets
        return assets

    def write_asset_documents(self):
        # type: () -> None
        """
        Writes generated JSON assets under the collection directory.
        """
        for path, content in self.asset_documents.items():
            self.write_json(os.path.join(self.collection_dir, path), content)

    def make_item(self, item_index):
        # type: (int) -> JSON
        """
        Generates an Item representing a shared result instance across aligned output IDs.
        """
        output_ids = [
            output_id for output_id, result in self.results.items()
            if not isinstance(result, list) or len(result) == self.item_count
        ]
        assets, values = self.make_assets(item_index)
        bbox = merge_bbox([
            self.extents[output_id][item_index][0]
            for output_id in output_ids
            if item_index < len(self.extents[output_id])
        ])
        descriptions = [
            self.output_definition(out_id).get("description")
            for out_id in output_ids
            if self.output_definition(out_id).get("description")
        ]
        keywords = list(dict.fromkeys(
            keyword
            for out_id in output_ids
            for keyword in self.output_definition(out_id).get("keywords") or []
        ))
        item_id = f"{self.job.id}-{item_index}"
        props = {
            **self.make_datetime_properties(item_index),
            "created": self.finished,
            "title": f"Result {item_index + 1} of Job {self.job.id}",
            "weaver:job_id": str(self.job.id),
            "weaver:process_id": self.job.process,
            "weaver:output_id": output_ids,
        }  # type: JSON
        if descriptions:
            props["description"] = " ".join(descriptions)
        if keywords:
            props["keywords"] = keywords
        if self.job.service:
            props["weaver:provider_id"] = self.job.service
        if values:
            props["weaver:value"] = values
            props["processing:expression"] = {
                "format": "results",
                "expression": values,
                "parameters": self.make_processing_parameters(),
            }
        props.update(self.make_processing_properties(output_ids))
        props.update(self.make_application_properties())

        extensions = [STAC_EXT_PROCESSING]
        if "application:languages" in props:
            extensions.append(STAC_EXT_APPLICATION)
        if any(key.startswith("file:") for asset in assets.values() for key in asset):
            extensions.append(STAC_EXT_FILE)

        item_url = self.item_url(item_id)
        links = [
            make_link(item_url, "self", f"Result Item [{item_id}].", ContentType.APP_GEOJSON),
            make_link(self.collection_url, "root", "Job results collection.", ContentType.APP_JSON),
            make_link(self.collection_url, "parent", "Job results collection.", ContentType.APP_JSON),
            make_link(self.collection_url, "collection", "Job results collection.", ContentType.APP_JSON),
        ]
        links.extend(
            make_link(
                f"{self.job_url}/results/{quote(output_id, safe='')}", "alternate",
                f"Job result of output [{output_id}].", ContentType.APP_JSON
            )
            for output_id in output_ids
        )
        links.extend(self.make_reference_links())
        return {
            "type": "Feature",
            "stac_version": STAC_VERSION,
            "stac_extensions": extensions,
            "id": item_id,
            "collection": str(self.job.id),
            "geometry": get_geojson_geometry(bbox),
            **({"bbox": bbox} if bbox else {}),
            "properties": props,
            "assets": assets,
            "links": links,
        }

    def make_extent(self, items):
        # type: (Dict[str, JSON]) -> JSON
        """
        Generates the :term:`STAC` Collection extent that contains the extents of all Items.

        If no spatial extent could be found from any result, the whole world is indicated as per :term:`STAC` guidance.
        """
        bbox = merge_bbox([
            extent[0]
            for output_extents in self.extents.values()
            for extent in output_extents
        ]) or STAC_WORLD_BBOX
        times = list(self.reference_datetimes)  # type: List[datetime]
        for item in items.values():
            for field in ["datetime", "start_datetime", "end_datetime"]:
                dt = parse_datetime(item["properties"].get(field) or "")
                if dt:
                    times.append(dt)
        interval = [to_rfc3339(min(times)), to_rfc3339(max(times))] if times else [None, None]
        return {"spatial": {"bbox": [bbox]}, "temporal": {"interval": [interval]}}

    def make_item_collection(self, items):
        # type: (Dict[str, JSON]) -> JSON
        """
        Generates the :term:`STAC` ItemCollection that lists Items, equivalent to ``/collections/{id}/items``.
        """
        items_url = self.job.collection_url(self.settings, STAC_ITEMS_FILE)
        return {
            "type": "FeatureCollection",
            "stac_version": STAC_VERSION,
            "features": list(items.values()),
            "numberMatched": len(items),
            "numberReturned": len(items),
            "links": [
                make_link(items_url, "self", "Job results items.", ContentType.APP_GEOJSON),
                make_link(self.collection_url, "root", "Job results collection.", ContentType.APP_JSON),
                make_link(self.collection_url, "parent", "Job results collection.", ContentType.APP_JSON),
                make_link(self.collection_url, "collection", "Job results collection.", ContentType.APP_JSON),
            ],
        }

    def make_collection(self, items):
        # type: (Dict[str, JSON]) -> JSON
        """
        Generates the :term:`STAC` Collection of the :term:`Job` results.
        """
        output_ids = list(self.results)
        process = self.process
        proc_title = (process.title if process is not None else None) or self.job.process
        keywords = list(process.keywords or []) if process is not None else []
        provider = {
            "name": self.settings.get("weaver.wps_metadata_provider_name") or __title__,
            "description": "Server that executed the process and generated the job results.",
            "roles": ["processor", "host"],
            "url": self.weaver_url or __source_repository__,
        }  # type: JSON
        provider.update(self.make_processing_properties())
        if isinstance(self.package, dict):
            provider["processing:expression"] = {
                "format": "cwl",
                "expression": self.package,
                "parameters": self.make_processing_parameters(),
            }
        provider.update(self.make_application_properties())

        extensions = [STAC_EXT_PROCESSING]
        if "application:languages" in provider:
            extensions.append(STAC_EXT_APPLICATION)
        if any(key.startswith("file:") for asset in self.collection_assets.values() for key in asset):
            extensions.append(STAC_EXT_FILE)

        links = [
            make_link(self.collection_url, "self", "Job results collection.", ContentType.APP_JSON),
            make_link(self.collection_url, "root", "Job results collection.", ContentType.APP_JSON),
        ]
        links.append(
            make_link(self.job.collection_url(self.settings, STAC_ITEMS_FILE), "items", "Job results items.",
                      ContentType.APP_GEOJSON)
        )
        links.extend(
            make_link(self.item_url(item_id), "item", f"Result Item [{item_id}].",
                      ContentType.APP_GEOJSON, id=item_id)
            for item_id in items
        )
        links.extend(self.make_reference_links())
        description = (process.description if process is not None else None) or ""
        description = f"Results of Job [{self.job.id}] from Process [{proc_title}]. {description}".strip()
        app_props = self.make_application_properties()
        return {
            "type": "Collection",
            "stac_version": STAC_VERSION,
            "stac_extensions": extensions,
            **app_props,
            "id": str(self.job.id),
            "title": f"Results of Job {self.job.id}",
            "description": description,
            "keywords": ["weaver", "job", "results", str(self.job.process)] + [str(kw) for kw in keywords],
            "license": STAC_LICENSE,
            "providers": [provider],
            "extent": self.make_extent(items),
            "summaries": {"weaver:output_id": output_ids},
            "assets": self.collection_assets,
            "links": links,
        }

    @staticmethod
    def write_json(path, content):
        # type: (Path, JSON) -> None
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
        try:
            with os.fdopen(fd, mode="w", encoding="utf-8") as tmp_file:
                json.dump(content, tmp_file, indent=2, ensure_ascii=False)
            os.chmod(tmp_path, 0o644)  # nosec: B103  # outputs are served statically like other job results
            os.replace(tmp_path, path)
        except BaseException:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def write(self):
        # type: () -> Path
        """
        Generates and writes all :term:`STAC` documents to the collection directory of the :term:`Job`.

        :returns: Path of the collection document.
        """
        self.resolve_extents()
        self.make_collection_assets()
        items = {
            f"{self.job.id}-{item_index}": self.make_item(item_index)
            for item_index in range(self.item_count)
        }
        self.write_asset_documents()
        if collection_api_url(self.settings):
            return self.post(items)
        for item_id, item in items.items():
            self.write_json(os.path.join(self.collection_dir, get_item_path(item_id)), item)
        self.write_json(os.path.join(self.collection_dir, STAC_ITEMS_FILE), self.make_item_collection(items))
        collection = self.make_collection(items)
        collection_file = os.path.join(self.collection_dir, STAC_COLLECTION_FILE)
        self.write_json(collection_file, collection)
        return collection_file

    def post(self, items):
        # type: (Dict[str, JSON]) -> Path
        """
        Publishes the :term:`STAC` Collection and Items to the configured :term:`STAC` API instead of static files.

        :returns: Path of the local marker file indicating the location of the published collection.
        """
        staging = collection_api_url(self.settings, staging=True)
        coll_url = f"{staging}/collections"
        collection = self.make_collection(items)
        self.delete_api(staging)
        self.request_api("POST", coll_url, collection)
        for item in items.values():
            self.request_api("POST", f"{coll_url}/{quote(str(self.job.id), safe='')}/items", item)
        marker = os.path.join(self.collection_dir, STAC_API_MARKER)
        self.write_json(marker, {"href": self.collection_url})
        return marker

    def delete_api(self, staging):
        # type: (URL) -> None
        try:
            request_extra("DELETE", f"{staging}/collections/{quote(str(self.job.id), safe='')}",
                          settings=self.settings, cache_enabled=False)
        except Exception as exc:  # noqa: W0703
            LOGGER.debug("Ignoring failed removal of previous STAC collection of job [%s]: [%s]", self.job.id, exc)

    def request_api(self, method, url, body):
        # type: (str, URL, JSON) -> None
        resp = request_extra(method, url, json=body, settings=self.settings, cache_enabled=False,
                             headers={"Content-Type": ContentType.APP_JSON, "Accept": ContentType.APP_JSON})
        if resp.status_code >= 400:
            raise IOError(f"STAC API request [{method} {url}] failed with status [{resp.status_code}].")


def generate_job_collection(job, settings, results, process=None, force=False):
    # type: (Job, AnySettingsContainer, ExecutionResults, Optional[Process], bool) -> Optional[Path]
    """
    Generates the static :term:`STAC` Collection and Items of a successful :term:`Job` according to its results.

    Errors are logged and ignored to avoid impacting the :term:`Job` status when the collection cannot be generated.

    :param job: Successful job for which to generate the collection.
    :param settings: Application settings.
    :param results: Results of the job using the :term:`OGC` mapping representation with resolved ``href`` values.
    :param process: Process definition from which the results were generated, if available.
    :param force: Regenerate the collection even if it already exists. Otherwise, the existing one is reused.
    :returns: Path of the collection document, or ``None`` if disabled, not applicable or on failure.
    """
    if not collection_enabled(settings):
        return None
    if not force and job.collection_exists(settings):
        api = collection_api_url(settings)
        return job.collection_path(settings, STAC_API_MARKER if api else STAC_COLLECTION_FILE)
    try:
        collection = JobCollection(job, settings, results, process)
        collection.resolve_extents()
        shutil.rmtree(job.collection_path(settings), ignore_errors=True)
        return collection.write()
    except AmbiguousCollectionItems:
        raise
    except Exception as exc:  # noqa: W0703
        LOGGER.warning("Failed generation of STAC collection of job [%s]: [%s]", job.id, exc, exc_info=exc)
    return None
