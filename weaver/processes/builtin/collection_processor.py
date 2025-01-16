#!/usr/bin/env python
"""
Retrieves relevant data or files resolved from a collection reference using its metadata, queries and desired outputs.
"""
import argparse
import inspect
import io
import json
import logging
import os
import sys
from typing import TYPE_CHECKING, cast

from owslib.ogcapi.coverages import Coverages
from owslib.ogcapi.features import Features
from owslib.ogcapi.maps import Maps
from pystac_client import ItemSearch
from pystac_client.stac_api_io import StacApiIO

CUR_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, CUR_DIR)
# root to allow 'from weaver import <...>'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(CUR_DIR))))

# place weaver specific imports after sys path fixing to ensure they are found from external call
# pylint: disable=C0413,wrong-import-order
from weaver.execute import ExecuteCollectionFormat  # isort:skip # noqa: E402
from weaver.formats import (  # isort:skip # noqa: E402
    ContentType,
    find_supported_media_types,
    get_cwl_file_format,
    get_extension
)
from weaver.processes.builtin.utils import (  # isort:skip # noqa: E402
    get_package_details,
    is_geojson_url,
    validate_reference
)
from weaver.processes.constants import PACKAGE_FILE_TYPE  # isort:skip # noqa: E402
from weaver.utils import Lazify, get_any_id, load_file, repr_json, request_extra  # isort:skip # noqa: E402
from weaver.wps_restapi import swagger_definitions as sd  # isort:skip # noqa: E402

if TYPE_CHECKING:
    from typing import List

    from pystac import Asset

    from weaver.typedefs import (
        CWL_IO_FileValue,
        CWL_IO_ValueMap,
        JobValueCollection,
        JSON,
        Path,
        ProcessInputOutputItem
    )
    from weaver.utils import LoggerHandler

PACKAGE_NAME, PACKAGE_BASE, PACKAGE_MODULE = get_package_details(__file__)

# setup logger since it is not run from the main 'weaver' app
LOGGER = logging.getLogger(PACKAGE_MODULE)
LOGGER.addHandler(logging.StreamHandler(sys.stdout))
LOGGER.setLevel(logging.INFO)

# process details
__version__ = "1.0"
__title__ = "Collection Processor"
__abstract__ = __doc__  # NOTE: '__doc__' is fetched directly, this is mostly to be informative

OUTPUT_CWL_JSON = "cwl.output.json"


def process_collection(collection_input, input_definition, output_dir, logger=LOGGER):  # pylint: disable=R1260
    # type: (JobValueCollection, ProcessInputOutputItem, Path, LoggerHandler) -> List[CWL_IO_FileValue]
    """
    Processor of a :term:`Collection`.

    This function is intended to be employed either as a standalone :term:`Builtin Process` (for validating resolution)
    or as an intermediate :term:`Collection` resolution when submitted as input for another :term:`Process` execution.

    :param collection_input:
        Collection Input parameters with minimally the URI to the collection used as reference.
        Can contain additional filtering or hint format parameters.
    :param input_definition:
        Process input definition that indicates the target types, formats and schema to retrieve from the collection.
    :param output_dir: Directory to write the output (provided by the :term:`CWL` definition).
    :param logger: Optional logger handler to employ.
    :return: Resolved data references.
    """
    input_id = get_any_id(input_definition)
    logger.log(  # pylint: disable=E1205 # false positive
        logging.INFO,
        "Process [{}] for input=[{}] got arguments:\ncollection_input={}\noutput_dir=[{}]",
        PACKAGE_NAME,
        input_id,
        Lazify(lambda: repr_json(collection_input, indent=2)),
        output_dir,
    )
    os.makedirs(output_dir, exist_ok=True)

    col_input = sd.ExecuteCollectionInput().deserialize(collection_input)  # type: JobValueCollection
    col_args = dict(col_input)
    col_href = col_href_valid = col_args.pop("collection")
    if not col_href_valid.endswith("/"):
        col_href_valid += "/"

    col_fmt = col_args.pop("format", None)
    if col_fmt not in ExecuteCollectionFormat.values():
        col_fmt = ExecuteCollectionFormat.GEOJSON

    # static GeoJSON can be either a file-like reference or a generic server endpoint (directory-like)
    if col_fmt == ExecuteCollectionFormat.GEOJSON and not is_geojson_url(col_href):
        validate_reference(col_href_valid, is_file=False)
    # otherwise, any other format involves an API endpoint interaction
    else:
        validate_reference(col_href_valid, is_file=False)

    # find which media-types are applicable for the destination input definition
    col_media_type = col_args.pop("type", None)
    if not col_media_type:
        col_media_type = find_supported_media_types(input_definition)
    if col_media_type and not isinstance(col_media_type, list):
        col_media_type = [col_media_type]

    # extract collection ID, either directly from URI or supplied by alternate identifier
    col_parts = col_href.rsplit("/collections/", 1)
    api_url, col_id = col_parts if len(col_parts) == 2 else (None, col_parts[0])
    col_id_alt = get_any_id(col_input, pop=True)
    col_id = col_id or col_id_alt
    timeout = col_args.pop("timeout", 10)

    # convert all query parameters to their corresponding function parameter name
    for arg in list(col_args):
        if "-" in arg:
            col_args[arg.replace("-", "_")] = col_args.pop(arg)

    logger.log(  # pylint: disable=E1205 # false positive
        logging.INFO,
        "Attempting resolution of collection [{}] as format [{}]",
        col_href,
        col_fmt,
    )
    resolved_files = []
    if col_fmt == ExecuteCollectionFormat.GEOJSON:
        # static GeoJSON FeatureCollection document
        col_resp = request_extra(
            "GET",
            col_href,
            queries=col_args,
            headers={"Accept": f"{ContentType.APP_GEOJSON},{ContentType.APP_JSON}"},
            timeout=timeout,
            retries=3,
            only_server_errors=False,
        )
        col_json = col_resp.json()
        if not (col_resp.status_code == 200 and "features" in col_json):
            raise ValueError(f"Could not parse [{col_href}] as a GeoJSON FeatureCollection.")

        for i, feat in enumerate(col_json["features"]):
            path = os.path.join(output_dir, f"feature-{i}.geojson")
            with open(path, mode="w", encoding="utf-8") as file:
                json.dump(feat, file)
            _, file_fmt = get_cwl_file_format(ContentType.APP_GEOJSON)
            file_obj = {"class": PACKAGE_FILE_TYPE, "path": f"file://{path}", "format": file_fmt}
            resolved_files.append(file_obj)

    elif col_fmt in [ExecuteCollectionFormat.STAC, ExecuteCollectionFormat.STAC_ITEMS]:
        # ignore unknown or enforced parameters
        known_params = set(inspect.signature(ItemSearch).parameters)
        known_params -= {"url", "method", "stac_io", "client", "collection", "ids", "modifier"}
        for param in set(col_args) - known_params:
            col_args.pop(param)

        search_url = f"{api_url}/search"
        search = ItemSearch(
            url=search_url,
            method="POST",
            stac_io=StacApiIO(timeout=timeout, max_retries=3),  # FIXME: add 'headers' with authorization/cookies?
            collections=col_id,
            **col_args
        )
        for item in search.items():
            for ctype in col_media_type:
                if col_fmt == ExecuteCollectionFormat.STAC_ITEMS:
                    # FIXME: could alternate Accept header for Items' representation be employed?
                    _, file_fmt = get_cwl_file_format(ContentType.APP_GEOJSON)
                    file_obj = {"class": PACKAGE_FILE_TYPE, "path": item.get_self_href(), "format": file_fmt}
                    resolved_files.append(file_obj)
                    continue
                for _, asset in item.get_assets(media_type=ctype):  # type: (..., Asset)
                    _, file_fmt = get_cwl_file_format(ctype)
                    file_obj = {"class": PACKAGE_FILE_TYPE, "path": asset.href, "format": file_fmt}
                    resolved_files.append(file_obj)

    elif col_fmt == ExecuteCollectionFormat.OGC_FEATURES:
        if str(col_args.get("filter_lang")) == "cql2-json":
            col_args["cql"] = col_args.pop("filter")
        search = Features(
            url=api_url,
            # FIXME: add 'auth' or 'headers' authorization/cookies?
            headers={"Accept": f"{ContentType.APP_GEOJSON}, {ContentType.APP_VDN_GEOJSON}, {ContentType.APP_JSON}"},
        )
        items = search.collection_items(col_id, **col_args)
        if items.get("type") != "FeatureCollection" or "features" not in items:
            raise ValueError(
                f"Collection [{col_href}] using format [{col_fmt}] did not return a GeoJSON FeatureCollection."
            )
        for i, feat in enumerate(items["features"]):
            # NOTE:
            #   since STAC is technically OGC API - Features compliant, both can be used interchangeably
            #   if media-types are non-GeoJSON and happen to contain STAC Assets, handle it as STAC transparently
            if "assets" in feat and col_media_type != [ContentType.APP_GEOJSON]:
                for _, asset in feat["assets"].items():  # type: (str, JSON)
                    if asset["type"] in col_media_type:
                        _, file_fmt = get_cwl_file_format(asset["type"])
                        file_obj = {"class": PACKAGE_FILE_TYPE, "path": asset["href"], "format": file_fmt}
                        resolved_files.append(file_obj)
            else:
                path = os.path.join(output_dir, f"feature-{i}.geojson")
                with open(path, mode="w", encoding="utf-8") as file:
                    json.dump(feat, file)
                _, file_fmt = get_cwl_file_format(ContentType.APP_GEOJSON)
                file_obj = {"class": PACKAGE_FILE_TYPE, "path": f"file://{path}", "format": file_fmt}
                resolved_files.append(file_obj)

    elif col_fmt == ExecuteCollectionFormat.OGC_COVERAGE:
        cov = Coverages(
            url=api_url,
            # FIXME: add 'auth' or 'headers' authorization/cookies?
            headers={"Accept": ContentType.APP_JSON},
        )
        # adjust subset representation to match expected tuples from utility
        subset = col_args.get("subset")
        if isinstance(subset, dict):
            col_args["subset"] = [
                (subset_dim, *subset_values)
                for subset_dim, subset_values in subset.items()
            ]
        ctype = (col_media_type or [ContentType.IMAGE_COG])[0]
        ext = get_extension(ctype, dot=False)
        path = os.path.join(output_dir, f"coverage.{ext}")
        with open(path, mode="wb") as file:
            data = cast(io.BytesIO, cov.coverage(col_id, **col_args)).getbuffer()
            file.write(data)
        _, file_fmt = get_cwl_file_format(ctype)
        file_obj = {"class": PACKAGE_FILE_TYPE, "path": f"file://{path}", "format": file_fmt}
        resolved_files.append(file_obj)

    elif col_fmt in ExecuteCollectionFormat.OGC_MAP:
        maps = Maps(
            url=api_url,
            # FIXME: add 'auth' or 'headers' authorization/cookies?
            headers={"Accept": ContentType.APP_JSON},
        )
        ctype = (col_media_type or [ContentType.IMAGE_COG])[0]
        ext = get_extension(ctype[0], dot=False)
        path = os.path.join(output_dir, f"map.{ext}")
        with open(path, mode="wb") as file:
            data = cast(io.BytesIO, maps.map(col_id, **col_args)).getbuffer()
            file.write(data)
        _, file_fmt = get_cwl_file_format(ctype)
        file_obj = {"class": PACKAGE_FILE_TYPE, "path": f"file://{path}", "format": file_fmt}
        resolved_files.append(file_obj)

    else:
        raise ValueError(f"Collection [{col_href}] could not be resolved. Unknown format [{col_fmt}].")

    if not resolved_files:
        raise ValueError(f"Could not extract any data or reference from input collection [{col_href}].")

    logger.log(logging.INFO, "Resolved collection [{}] returned {} reference(s).", col_href, len(resolved_files))
    logger.log(  # pylint: disable=E1205 # false positive
        logging.DEBUG,
        "Resolved collection [{}] files:\n{}",
        col_href,
        Lazify(lambda: repr_json(resolved_files, indent=2)),
    )
    return resolved_files


def process_cwl(collection_input, input_definition, output_dir):
    # type: (JobValueCollection, ProcessInputOutputItem, Path) -> CWL_IO_ValueMap
    files = process_collection(collection_input, input_definition, output_dir)
    outputs = {"referenceOutput": files}  # output ID must match the one used in CWL definition
    with open(os.path.join(output_dir, OUTPUT_CWL_JSON), mode="w", encoding="utf-8") as file:
        json.dump(outputs, file)
    return outputs


def main(*args):
    # type: (*str) -> None
    LOGGER.info("Process [%s] Parsing inputs...", PACKAGE_NAME)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-c", "--collection",
        metavar="COLLECTION_INPUT",
        required=True,
        help="Collection Input parameters as JSON file path.",
    )
    parser.add_argument(
        "-p",
        metavar="PROCESS_INPUT",
        required=True,
        help="Process Input definition as JSON file path.",
    )
    parser.add_argument(
        "-o",
        metavar="OUTDIR",
        required=True,
        help="Output directory of the retrieved data.",
    )
    ns = parser.parse_args(*args)
    LOGGER.info("Process [%s] Loading collection input '%s'.", PACKAGE_NAME, ns.c)
    col_in = load_file(ns.c)
    LOGGER.info("Process [%s] Loading process input definition '%s'.", PACKAGE_NAME, ns.p)
    proc_in = load_file(ns.p)
    sys.exit(process_cwl(col_in, proc_in, ns.o) is not None)


if __name__ == "__main__":
    main()
