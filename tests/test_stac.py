import json
import os
import struct
import tempfile
import uuid
from copy import deepcopy
from typing import TYPE_CHECKING

import mock
import pystac
import pytest

from weaver import ogc_definitions as ogc_def
from weaver.collections.stac import (
    STAC_COLLECTION_FILE,
    STAC_EXT_APPLICATION,
    STAC_EXT_FILE,
    STAC_EXT_PROCESSING,
    AmbiguousCollectionItems,
    JobCollection,
    generate_job_collection,
    get_collection_dir_name,
    get_item_path,
    get_tiff_byte_order,
    is_wgs84,
    load_json_file
)
from weaver.collections.utils import collection_api_url, collection_enabled
from weaver.datatype import Job, Process
from weaver.formats import ContentType
from weaver.processes.constants import CWL_REQUIREMENT_SECRETS
from weaver.status import Status
from weaver.utils import compute_file_checksum, compute_file_digest_multibase

if TYPE_CHECKING:
    from typing import Dict, Optional, Tuple

    from weaver.typedefs import JSON, SettingsType


def make_settings(out_dir, **kwargs):
    # type: (str, ...) -> SettingsType
    settings = {
        "weaver.url": "https://localhost",
        "weaver.wps_output_dir": out_dir,
        "weaver.wps_output_url": "https://localhost/wpsoutputs",
        "weaver.wps_output_context": "",
    }
    settings.update(kwargs)
    return settings


def make_job(process="test-process", context=None):
    # type: (str, Optional[str]) -> Job
    job = Job(task_id=str(uuid.uuid4()), process=process, context=context, status=Status.SUCCEEDED)
    job.inputs = [{"id": "data", "href": "https://example.com/input.txt"}]
    job.mark_finished()
    return job


def make_results(settings, job, content=b"hello"):
    # type: (SettingsType, Job, bytes) -> JSON
    out_dir = os.path.join(settings["weaver.wps_output_dir"], str(job.context or ""), str(job.id), "out")
    os.makedirs(out_dir)
    path = os.path.join(out_dir, "result.txt")
    with open(path, "wb") as f:
        f.write(content)
    href = f"https://localhost/wpsoutputs/{job.id}/out/result.txt"
    if job.context:
        href = f"https://localhost/wpsoutputs/{job.context}/{job.id}/out/result.txt"
    return {
        "out": {"href": href, "type": "text/plain", "digestMultibase": compute_file_digest_multibase(path)},
        "value": {"value": 3, "dataType": "integer"},
    }


@pytest.mark.parametrize(
    ["context", "expect"],
    [
        (None, ""),
        ("ctx/sub", "ctx/sub/"),
    ],
)
@pytest.mark.collection
def test_job_collection_url_path(context, expect):
    """
    Tests that the collection location is stored next to the job results and provenance directories.
    """
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp)
        job = make_job(context=context)
        name = get_collection_dir_name(job.id)
        assert name == f"{job.id}-collection"
        assert job.collection_url(settings) == f"https://localhost/wpsoutputs/{expect}{name}/{STAC_COLLECTION_FILE}"
        assert job.collection_path(settings) == os.path.join(tmp, *filter(None, expect.split("/")), name)
        assert job.collection_url(settings, get_item_path("out")).endswith(f"{name}/items/out.json")


@pytest.mark.collection
def test_job_collection_links_absent_until_generated():
    """
    Tests that job links only advertise the collection once the documents exist.
    """
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp)
        job = make_job()
        assert not job.collection_exists(settings)
        assert not [lnk for lnk in job.links(settings) if "collection.json" in lnk["href"]]
        status_link = [
            lnk for lnk in job.links(settings)
            if lnk["rel"] == "collection" and "profile" in lnk
        ]
        assert len(status_link) == 1
        assert status_link[0]["href"] == f"{job.results_url(settings)}?response=collection"
        assert status_link[0]["profile"] == "https://www.opengis.net/def/profile/OGC/0/ogc-collection"
        result_link = job.collection_links(settings, "results")[0]
        assert result_link["rel"] == "alternate"
        assert result_link["href"] == status_link[0]["href"]
        assert result_link["profile"] == status_link[0]["profile"]
        results = make_results(settings, job)
        job.results = [{"id": "out", "href": results["out"]["href"]}, {"id": "value", "data": 3}]
        assert generate_job_collection(job, settings, results) is not None
        status_link = [
            lnk for lnk in job.links(settings)
            if lnk["rel"] == "collection" and "profile" in lnk
        ]
        assert len(status_link) == 1
        assert status_link[0]["href"] == f"{job.results_url(settings)}?response=collection"
        result_link = job.collection_links(settings, "results")[0]
        assert result_link["rel"] == "alternate"
        assert result_link["href"] == job.collection_url(settings)
        assert result_link["profile"] == status_link[0]["profile"]


@pytest.mark.collection
@pytest.mark.stac
def test_job_collection_generation():
    """
    Tests that STAC Collection and Items are valid, use the extensions and describe the files of the job results.
    """
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp)
        job = make_job()
        results = make_results(settings, job, b"hello")
        path = generate_job_collection(job, settings, results)
        assert path and os.path.isfile(path)
        coll_dir = job.collection_path(settings)

        with open(path, mode="r", encoding="utf-8") as f:
            coll_data = json.load(f)
        assert coll_data["id"] == str(job.id)
        assert coll_data["type"] == "Collection"
        assert coll_data["stac_version"] == "1.1.0"
        assert coll_data["license"] == "other"
        assert coll_data["providers"][0]["processing:level"] == "L4"
        link_rels = {lnk["rel"] for lnk in coll_data["links"]}
        assert {"processing-execution", "processing-expression", "derived_from", "items"} <= link_rels
        with open(os.path.join(coll_dir, "items", "index.json"), mode="r", encoding="utf-8") as f:
            index = json.load(f)
        assert index["type"] == "FeatureCollection"
        assert index["numberMatched"] == index["numberReturned"] == 1
        assert STAC_EXT_PROCESSING in coll_data["stac_extensions"]
        coll = pystac.Collection.from_dict(coll_data)
        assert coll.id == str(job.id)

        with open(os.path.join(coll_dir, "items", f"{job.id}-0.json"), mode="r", encoding="utf-8") as f:
            item_data = json.load(f)
        pystac.Item.from_dict(item_data)
        assert STAC_EXT_FILE in item_data["stac_extensions"]
        assert STAC_EXT_PROCESSING in item_data["stac_extensions"]
        assert item_data["collection"] == str(job.id)
        assert item_data["properties"]["weaver:output_id"] == ["out", "value"]
        asset = item_data["assets"]["out"]
        assert "processing-output" in asset["roles"]
        assert asset["file:size"] == 5
        assert asset["file:checksum"] == compute_file_checksum(
            os.path.join(tmp, str(job.id), "out", "result.txt"), "sha256"
        )
        assert asset["type"] == "text/plain"
        rels = {lnk["rel"] for lnk in item_data["links"]}
        assert {"self", "root", "parent", "collection"} <= rels

        assert item_data["properties"]["weaver:value"] == {"value": 3}
        assert coll_data["assets"]["parameters"]["roles"] == ["data", "processing-parameters"]
        assert coll_data["assets"]["results"]["roles"] == ["data", "processing-results"]
        assert os.path.isfile(os.path.join(coll_dir, "assets", "parameters.json"))


@pytest.mark.collection
def test_job_collection_disabled():
    """
    Tests that no collection is generated nor advertised when explicitly disabled by configuration.
    """
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp, **{"weaver.job_collection": "false"})
        job = make_job()
        results = make_results(settings, job)
        assert not collection_enabled(settings)
        assert generate_job_collection(job, settings, results) is None
        assert not os.path.exists(job.collection_path(settings))
        assert not job.collection_exists(settings)


@pytest.mark.stac
@pytest.mark.parametrize(
    ["header", "expect"],
    [
        (b"II*\x00" + struct.pack("<I", 8), "little-endian"),
        (b"MM\x00*" + struct.pack(">I", 8), "big-endian"),
        (b"not a tiff", None),
    ],
)
def test_get_tiff_byte_order(header, expect):
    """
    Tests detection of the byte order from TIFF headers for the STAC File extension.
    """
    with tempfile.NamedTemporaryFile(suffix=".tif", delete=False) as tmp:
        tmp.write(header)
    try:
        assert get_tiff_byte_order(tmp.name) == expect
    finally:
        os.remove(tmp.name)


@pytest.mark.stac
def test_compute_file_checksum():
    """
    Tests that the STAC file checksum is the hex multihash consistent with the multibase digest.
    """
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"hello")
    try:
        checksum = compute_file_checksum(tmp.name, "sha256")
        assert checksum.startswith("1220") and len(checksum) == 68
        assert checksum == checksum.lower()
    finally:
        os.remove(tmp.name)


@pytest.mark.collection
@pytest.mark.stac
def test_job_collection_process_application_extension():
    """
    Tests that process and CWL package references are mapped to the STAC Application extension.
    """
    package = {
        "cwlVersion": "v1.2",
        "class": "CommandLineTool",
        "baseCommand": ["echo"],
        "requirements": {"DockerRequirement": {"dockerPull": "debian:latest"}},
        "inputs": {},
        "outputs": {},
    }
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp)
        job = make_job()
        results = make_results(settings, job)
        process = Process(id="test-process", package=package, title="Test", version="1.2.3", keywords=["a"])
        path = generate_job_collection(job, settings, results, process)
        with open(path, mode="r", encoding="utf-8") as f:
            coll = json.load(f)
        assert STAC_EXT_APPLICATION in coll["stac_extensions"]
        assert coll["application:languages"] == ["CWL"]
        assert coll["application:entrypoint"] == "echo"
        assert coll["providers"][0]["processing:expression"]["expression"] == package
        assert coll["providers"][0]["processing:expression"]["parameters"] == {
            "data": {"href": "https://example.com/input.txt"}
        }
        assert "Test" in coll["description"]


@pytest.mark.collection
@pytest.mark.stac
@pytest.mark.parametrize(
    "inputs",
    [
        {"numbers": [1, 2, 3], "text": {"value": "sample"}},
        [
            {"id": "numbers", "value": 1},
            {"id": "numbers", "value": 2},
            {"id": "numbers", "value": 3},
            {"id": "text", "value": "sample"},
        ],
        [{"id": "numbers", "value": [1, 2, 3]}, {"id": "text", "value": "sample"}],
    ],
)
def test_job_collection_processing_parameters_preserve_arrays(inputs):
    """
    Tests that array-valued named inputs remain arrays in Processing Extension metadata.
    """
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp)
        job = make_job()
        job.inputs = deepcopy(inputs)
        path = generate_job_collection(job, settings, {"value": {"value": 1}})
        assert path
        with open(os.path.join(job.collection_path(settings), "assets", "parameters.json"), encoding="utf-8") as f:
            params = json.load(f)
        assert params == {"numbers": [1, 2, 3], "text": "sample"}
        assert job.inputs == inputs


@pytest.mark.collection
@pytest.mark.stac
@pytest.mark.parametrize("schema", [dict, list])
def test_job_collection_input_format_metadata(schema):
    """
    Tests that input normalization preserves file references and format metadata without modifying the job inputs.
    """
    file_input = {"href": "https://example.com/input.geojson", "format": {"mimeType": ContentType.APP_GEOJSON}}
    inputs = {"data": file_input} if schema is dict else [{"id": "data", **file_input}]
    with tempfile.TemporaryDirectory() as tmp:
        job = make_job()
        job.inputs = deepcopy(inputs)
        collection = JobCollection(job, make_settings(tmp), {})
        assert collection.make_processing_parameters() == {"data": {"href": file_input["href"]}}
        input_links = [link for link in collection.make_reference_links() if link["rel"] == "derived_from"]
        assert input_links[0]["href"] == file_input["href"]
        assert input_links[0]["type"] == ContentType.APP_GEOJSON
        assert job.inputs == inputs


@pytest.mark.collection
@pytest.mark.stac
@pytest.mark.parametrize(
    "value",
    [
        {"mimeType": ContentType.APP_GEOJSON},
        {"mediaType": ContentType.APP_GEOJSON},
        {"contentMediaType": ContentType.APP_GEOJSON},
        {"format": {"mimeType": ContentType.APP_GEOJSON}},
        {"format": {"mediaType": ContentType.APP_GEOJSON}},
        {"format": ContentType.APP_GEOJSON},
        {"type": ContentType.APP_GEOJSON},
    ],
)
def test_job_collection_media_type_fields(value):
    """
    Tests that STAC metadata accepts supported media-type field aliases from result and format definitions.
    """
    assert JobCollection.get_media_type(value) == ContentType.APP_GEOJSON


@pytest.mark.collection
@pytest.mark.stac
def test_job_collection_masks_secret_processing_parameters():
    """
    Tests that CWL inputs declared as secrets are masked in generated Collection metadata and sidecar assets.
    """
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp)
        job = make_job()
        job.inputs = [{"id": "token", "value": "do-not-publish-this"}]
        results = {"value": {"value": "done"}}
        process = Process(
            id=job.process,
            package={"hints": {CWL_REQUIREMENT_SECRETS: {"secrets": ["token"]}}},
        )
        generate_job_collection(job, settings, results, process)
        collection_dir = job.collection_path(settings)
        content = []
        for root, _, files in os.walk(collection_dir):
            for file_name in files:
                with open(os.path.join(root, file_name), mode="r", encoding="utf-8") as file:
                    content.append(file.read())
        assert all("do-not-publish-this" not in item for item in content)


def make_job_with_files(settings, files):
    # type: (SettingsType, Dict[str, Tuple[str, str]]) -> Tuple[Job, JSON]
    """
    Creates a job with results files from ``{output_id: (file_name, content)}``.
    """
    job = make_job()
    out_dir = os.path.join(settings["weaver.wps_output_dir"], str(job.id))
    os.makedirs(out_dir)
    results = {}
    for out_id, (name, content) in files.items():
        with open(os.path.join(out_dir, name), mode="w", encoding="utf-8") as f:
            f.write(content)
        results[out_id] = {"href": f"https://localhost/wpsoutputs/{job.id}/{name}", "type": "application/geo+json"}
    return job, results


def load_item(job, settings, item_id=None):
    # type: (Job, SettingsType, Optional[str]) -> JSON
    item_id = item_id or f"{job.id}-0"
    with open(os.path.join(job.collection_path(settings), "items", f"{item_id}.json"), encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.collection
@pytest.mark.stac
@pytest.mark.parametrize(
    ["media_type", "expected"],
    [
        *[(media_type, True) for media_type in sorted(
            ContentType.ANY_GEOJSON | ContentType.ANY_NETCDF | ContentType.ANY_TIFF
        )],
        (f"{ContentType.APP_GEOJSON}; charset=UTF-8", True),
        (ContentType.APP_GEOJSON.upper(), True),
        ("iana:application/geo+json", True),
        (ContentType.APP_JSON, False),
        (ContentType.TEXT_PLAIN, False),
        ("application/not-geotiff", False),
    ],
)
def test_job_collection_geospatial_media_types(media_type, expected):
    """
    Tests that geospatial result detection resolves supported media types and their format parameters.
    """
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp)
        process = Process(id="test-process", package={}, outputs=[
            {"id": "out", "formats": [{"mediaType": media_type}]},
        ])
        collection = JobCollection(make_job(), settings, {}, process)
        assert collection.is_geospatial_result("out", []) is expected
        assert collection.is_geospatial_result("other", [{"type": media_type}]) is expected


@pytest.mark.collection
@pytest.mark.stac
@pytest.mark.parametrize(
    ["href", "expected"],
    [
        ("https://example.com/result.geojson?download=true", True),
        ("https://example.com/result.tiff#data", True),
        ("https://example.com/result.nc", True),
        ("https://example.com/result.txt", False),
    ],
)
def test_job_collection_geospatial_file_formats(href, expected):
    """
    Tests that referenced result formats are detected from URL path extensions.
    """
    with tempfile.TemporaryDirectory() as tmp:
        collection = JobCollection(make_job(), make_settings(tmp), {})
        assert collection.is_geospatial_result("out", [{"href": href}]) is expected


@pytest.mark.stac
@pytest.mark.parametrize(
    "media_type",
    [ContentType.APP_JSON, ContentType.APP_GEOJSON, f"{ContentType.APP_GEOJSON}; charset=UTF-8"],
)
def test_load_json_file_media_type(media_type):
    """
    Tests that JSON result metadata is read for JSON media types with or without format parameters.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".data", encoding="utf-8") as file:
        json.dump({"value": 3}, file)
        file.flush()
        assert load_json_file(file.name, media_type) == {"value": 3}


@pytest.mark.collection
@pytest.mark.stac
@pytest.mark.parametrize(
    ["crs", "expected"],
    [
        *[(crs, True) for crs in ogc_def.OGC_DEF_CRS_ANY_EPSG4326],
        (None, True),
        ({"uri": ogc_def.OGC_DEF_CRS_CRS84_URI}, True),
        ({"properties": {"name": ogc_def.OGC_DEF_CRS_EPSG4326_URN}}, True),
        ("EPSG:3857", False),
        ("https://example.com/CRS84", False),
    ],
)
def test_job_collection_wgs84_crs(crs, expected):
    """
    Tests that collection extents recognize the shared OGC geographic CRS definitions.
    """
    assert is_wgs84(crs) is expected


@pytest.mark.collection
@pytest.mark.stac
def test_job_collection_geometry_from_geojson():
    """
    Tests that item geometry and collection extent are derived from the largest extent of GeoJSON results.
    """
    geojson = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [10.0, 20.0]}, "properties": {}}
    bbox_json = {"type": "FeatureCollection", "bbox": [-5, -6, 7, 8], "features": []}
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp)
        job, results = make_job_with_files(settings, {
            "point": ("point.geojson", json.dumps(geojson)),
            "area": ("area.geojson", json.dumps(bbox_json)),
        })
        path = generate_job_collection(job, settings, results)
        with open(path, encoding="utf-8") as f:
            coll = json.load(f)
        item = load_item(job, settings)
        assert item["bbox"] == [-5, -6, 10.0, 20.0]
        assert item["geometry"]["type"] == "Polygon"
        assert coll["extent"]["spatial"]["bbox"] == [[-5, -6, 10.0, 20.0]]


@pytest.mark.collection
@pytest.mark.stac
def test_job_collection_aligns_output_arrays_by_cardinality():
    """
    Tests that a shared geo-like array cardinality aligns outputs into Items and keeps unmatched arrays at Collection
    level.
    """
    def feature(x):
        # type: (int) -> JSON
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [x, 20]},
            "properties": {},
        }

    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp)
        job = make_job()
        results = {
            "geo_a": [feature(1), feature(2)],
            "geo_b": [feature(3), feature(4)],
            "geo_unmatched": [feature(5), feature(6), feature(7)],
            "literal": {"value": "shared"},
        }
        path = generate_job_collection(job, settings, results)
        assert path and os.path.isfile(path)
        with open(path, encoding="utf-8") as f:
            collection = json.load(f)
        with open(os.path.join(job.collection_path(settings), "items", "index.json"), encoding="utf-8") as f:
            index = json.load(f)
        assert index["numberReturned"] == 2
        first = load_item(job, settings)
        second = load_item(job, settings, f"{job.id}-1")
        assert first["properties"]["weaver:output_id"] == ["geo_a", "geo_b", "literal"]
        assert second["properties"]["weaver:value"] == {"literal": "shared"}
        assert first["properties"]["weaver:value"] == {"literal": "shared"}
        assert first["bbox"] == [1, 20, 3, 20]
        assert second["bbox"] == [2, 20, 4, 20]
        assert set(first["assets"]) == {"geo_a", "geo_b"}
        assert first["assets"]["geo_a"]["href"].endswith(f"/assets/items/{job.id}-0/geo_a.json")
        assert len([key for key in collection["assets"] if key.startswith("output-geo_unmatched-")]) == 3
        assert all(
            "processing-output" in asset["roles"]
            for key, asset in collection["assets"].items()
            if key.startswith("output-geo_unmatched-")
        )


@pytest.mark.collection
@pytest.mark.stac
@pytest.mark.parametrize(
    "lengths",
    [
        (2, 3),
        (2, 3, 4),
        (0,),
    ],
)
def test_job_collection_rejects_ambiguous_output_arrays(lengths):
    """
    Tests that geo-like arrays without a unique usable cardinality are rejected instead of producing misleading Items.
    """
    feature = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 2]}, "properties": {}}
    results = {f"geo_{index}": [feature] * length for index, length in enumerate(lengths)}
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp)
        job = make_job()
        process = Process(
            id=job.process,
            package={},
            outputs=[{"id": out_id, "formats": [{"mediaType": "application/geo+json"}]} for out_id in results]
        )
        with pytest.raises(AmbiguousCollectionItems, match="cardinalit|no items"):
            generate_job_collection(job, settings, results, process)
        assert not os.path.exists(job.collection_path(settings))


@pytest.mark.collection
@pytest.mark.stac
def test_job_collection_cardinality_uses_matching_non_geo_arrays():
    """
    Tests that non-geo output arrays contribute to resolving the most common geo-like result cardinality.
    """
    feature = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [1, 2]}, "properties": {}}
    results = {
        "geo_two": [feature, feature],
        "geo_three": [feature, feature, feature],
        "text": ["a", "b", "c"],
    }
    process = Process(
        id="test-process",
        package={},
        outputs=[
            {"id": "geo_two", "formats": [{"mediaType": "application/geo+json"}]},
            {"id": "geo_three", "formats": [{"mediaType": "application/geo+json"}]},
            {"id": "text", "formats": [{"mediaType": "text/plain"}]},
        ],
    )
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp)
        job = make_job()
        path = generate_job_collection(job, settings, results, process)
        assert path and os.path.isfile(path)
        with open(os.path.join(job.collection_path(settings), "items", "index.json"), encoding="utf-8") as f:
            index = json.load(f)
        assert index["numberReturned"] == 3
        assert load_item(job, settings)["properties"]["weaver:output_id"] == ["geo_three", "text"]
        with open(path, encoding="utf-8") as f:
            collection = json.load(f)
        assert "output-geo_two-0" in collection["assets"]


@pytest.mark.collection
@pytest.mark.stac
def test_job_collection_datetime_from_inputs_and_fallback():
    """
    Tests that datetime values from results are used as reference, otherwise the job time is employed.
    """
    feature = {
        "type": "Feature", "geometry": None,
        "properties": {"start_datetime": "2020-01-01T00:00:00Z", "end_datetime": "2020-02-01T00:00:00Z"},
    }
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp)
        job, results = make_job_with_files(settings, {"feat": ("feat.geojson", json.dumps(feature))})
        job.results = []
        generate_job_collection(job, settings, results)
        props = load_item(job, settings)["properties"]
        assert props["start_datetime"].startswith("2020-01-01")
        assert props["end_datetime"].startswith("2020-02-01")
        assert props["datetime"] is None

    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp)
        job, results = make_job_with_files(settings, {"txt": ("a.txt", "no datetime")})
        generate_job_collection(job, settings, results)
        props = load_item(job, settings)["properties"]
        assert props["datetime"] is not None, "job time fallback expected"
        assert load_item(job, settings)["geometry"] is None


@pytest.mark.collection
def test_job_collection_reuse_and_force():
    """
    Tests that an existing collection is reused unless regeneration is forced.
    """
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp)
        job, results = make_job_with_files(settings, {"txt": ("a.txt", "data")})
        path = generate_job_collection(job, settings, results)
        marker = os.path.join(os.path.dirname(path), "marker")
        with open(marker, mode="w", encoding="utf-8") as f:
            f.write("x")
        assert generate_job_collection(job, settings, results) == path
        assert os.path.exists(marker), "existing collection must be reused"
        assert generate_job_collection(job, settings, results, force=True) == path
        assert not os.path.exists(marker), "forced collection must be regenerated"
        assert os.path.isfile(path)


@pytest.mark.collection
@pytest.mark.stac
def test_job_collection_stac_api_urls():
    """
    Tests that public and staging STAC API URLs are resolved, and contents are posted to the staging one.
    """
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp, **{"weaver.job_collection_stac_api_public_url": "https://public/stac/"})
        job, results = make_job_with_files(settings, {"txt": ("a.txt", "data")})
        assert collection_api_url(settings) == "https://public/stac"
        assert collection_api_url(settings, staging=True) == "https://public/stac"
        assert job.collection_url(settings) == f"https://public/stac/collections/{job.id}"
        assert job.collection_url(settings, "items/txt.json") == f"https://public/stac/collections/{job.id}/items/txt"
        settings["weaver.job_collection_stac_api_staging_url"] = "http://staging:8080"
        assert collection_api_url(settings) == "https://public/stac"
        assert collection_api_url(settings, staging=True) == "http://staging:8080"
        resp = mock.Mock(status_code=201)
        with mock.patch("weaver.collections.stac.request_extra", return_value=resp) as mocked:
            assert generate_job_collection(job, settings, results) is not None
        calls = [(c.args[0], c.args[1]) for c in mocked.call_args_list]
        assert ("POST", "http://staging:8080/collections") in calls
        assert ("POST", f"http://staging:8080/collections/{job.id}/items") in calls
        assert all(url.startswith("http://staging:8080") for _, url in calls)
        posted = [c.kwargs["json"] for c in mocked.call_args_list if c.args[0] == "POST"]
        assert posted[0]["links"][0]["href"].startswith("https://public/stac/collections/")
        assert posted[0]["assets"]["results"]["href"] == (
            f"https://localhost/wpsoutputs/{job.id}-collection/assets/results.json"
        )
        item_asset_hrefs = [asset["href"] for asset in posted[1]["assets"].values()]
        assert f"https://localhost/wpsoutputs/{job.id}/a.txt" in item_asset_hrefs
        collection_dir = job.collection_path(settings)
        assert os.path.isfile(os.path.join(collection_dir, ".stac-api"))
        assert os.path.isfile(os.path.join(collection_dir, "assets", "results.json"))
        assert not os.path.exists(os.path.join(collection_dir, "collection.json"))
        assert not os.path.exists(os.path.join(collection_dir, "items"))
        assert job.collection_exists(settings)


@pytest.mark.collection
@pytest.mark.stac
def test_job_collection_literal_expression():
    """
    Tests that literal results are also provided as processing expression of format results.
    """
    with tempfile.TemporaryDirectory() as tmp:
        settings = make_settings(tmp)
        job = make_job()
        results = {"value": {"value": 3, "dataType": "integer"}}
        generate_job_collection(job, settings, results)
        props = load_item(job, settings)["properties"]
        assert props["processing:expression"] == {
            "format": "results",
            "expression": {"value": 3},
            "parameters": {"data": {"href": "https://example.com/input.txt"}},
        }
