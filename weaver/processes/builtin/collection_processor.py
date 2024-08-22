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

from pystac_client import ItemSearch
from pystac_client.stac_api_io import StacApiIO
from owslib.ogcapi.coverages import Coverages
from owslib.ogcapi.features import Features
from owslib.ogcapi.maps import Maps

CUR_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, CUR_DIR)
# root to allow 'from weaver import <...>'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(CUR_DIR))))

# place weaver specific imports after sys path fixing to ensure they are found from external call
# pylint: disable=C0413,wrong-import-order
from weaver.execute import ExecuteCollectionFormat  # isort:skip # noqa: E402
from weaver.formats import ContentType, get_extension, find_supported_media_types  # isort:skip # noqa: E402
from weaver.processes.builtin.utils import (  # isort:skip # noqa: E402
    get_package_details,
    is_geojson_url,
    validate_reference
)
from weaver.utils import Lazify, load_file, repr_json, request_extra  # isort:skip # noqa: E402
from weaver.wps_restapi import swagger_definitions as sd  # isort:skip # noqa: E402

if TYPE_CHECKING:
    from pystac import Asset

    from weaver.typedefs import JSON, JobValueCollection, ProcessInputOutputItem

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


def process(collection_input, input_definition, output_dir):
    # type: (JobValueCollection, ProcessInputOutputItem, os.PathLike[str]) -> None
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
    :return: Resolved data references.
    """
    LOGGER.info(
        "Process [%s] Got arguments: collection_input=%s output_dir=%s",
        PACKAGE_NAME,
        Lazify(lambda: repr_json(collection_input, indent=2)),
        output_dir,
    )
    col_input = sd.ExecuteCollectionInput().deserialize(collection_input)  # type: JobValueCollection
    col_args = dict(col_input)
    col_file = col_ref = col_args.pop("collection")
    if not col_ref.endswith("/"):
        col_ref += "/"

    col_fmt = col_args.pop("format", None)
    if col_fmt not in ExecuteCollectionFormat.values():
        col_fmt = ExecuteCollectionFormat.GEOJSON

    # static GeoJSON can be either a file-like reference or a generic server endpoint (directory-like)
    if col_fmt == ExecuteCollectionFormat.GEOJSON and not is_geojson_url(col_file):
        validate_reference(col_ref, is_file=False)
    # otherwise, any other format involves an API endpoint interaction
    else:
        validate_reference(col_ref, is_file=False)

    # find which media-types are applicable for the destination input definition
    col_media_type = col_args.pop("type", None)
    if not col_media_type:
        col_media_type = find_supported_media_types(input_definition)
    if col_media_type and not isinstance(col_media_type, list):
        col_media_type = [col_media_type]

    api_url, col_id = col_ref.rsplit("/collections/", 1)

    # convert all parameters to their corresponding name of the query utility
    # all OWSLib utilities use (**kwargs) allowing additional parameters that will be ignored
    # others must parse/exclude unknown parameters to avoid errors
    for arg in list(col_args):
        if "-" in arg:
            col_args[arg.replace("-", "_")] = col_args.pop(arg)
    col_args.setdefault("timeout", 10)

    resolved_files = []
    if col_fmt == ExecuteCollectionFormat.GEOJSON:
        col_resp = request_extra(
            "GET",
            col_file,
            queries=col_args,
            headers={"Accept": f"{ContentType.APP_GEOJSON},{ContentType.APP_JSON}"},
            timeout=10,
            retries=3,
            only_server_errors=False,
        )
        if not (col_resp.status_code == 200 and "features" in col_resp.json):
            raise ValueError(f"Could not parse [{col_file}] as a GeoJSON FeatureCollection!")

        for i, feat in enumerate(col_resp.json["features"]):
            path = os.path.join(output_dir, f"feature-{i}.geojson")
            with open(path, mode="w", encoding="utf-8") as file:
                json.dump(feat, file)
            resolved_files.append(f"file://{path}")

    elif col_fmt == ExecuteCollectionFormat.STAC:
        known_params = set(inspect.signature(ItemSearch).parameters)
        known_params -= {"url", "method", "stac_io", "client", "collection", "ids", "modifier"}
        for param in set(col_args) - known_params:
            col_args.pop(param)

        timeout = col_args.pop("timeout", 10)
        search = ItemSearch(
            url=api_url,
            method="POST",
            stac_io=StacApiIO(timeout=timeout, max_retries=3),  # FIXME: add auth via 'headers'?
            collections=col_id,
            **col_args
        )
        for item in search.items():
            for ctype in col_media_type:
                for _, asset in item.get_assets(media_type=ctype):  # type: (..., Asset)
                    resolved_files.append(asset.href)

    elif col_fmt == ExecuteCollectionFormat.OGC_FEATURES:
        if str(col_args.get("filter_lang")) == "cql2-json":
            col_args["cql"] = col_args["filter"]
        search = Features(
            url=api_url,
            # FIXME: add 'auth' or 'headers'?
        )
        for i, feat in enumerate(search.collection_items(col_id, **col_args)):
            # NOTE:
            #   since STAC is technically OGC API - Features compliant, both can be used interchangeably
            #   if media-types are non-GeoJSON and happen to contain STAC Assets, handle it as STAC transparently
            if "assets" in feat and col_media_type != [ContentType.APP_GEOJSON]:
                for name, asset in feat["assets"].items():  # type: (str, JSON)
                    if asset["type"] in col_media_type:
                        resolved_files.append(asset["href"])
            else:
                path = os.path.join(output_dir, f"feature-{i}.geojson")
                with open(path, mode="w", encoding="utf-8") as file:
                    json.dump(feat, file)
                resolved_files.append(f"file://{path}")

    elif col_fmt == ExecuteCollectionFormat.OGC_COVERAGE:
        cov = Coverages(
            url=api_url,
            # FIXME: add 'auth' or 'headers'?
        )
        ctype = col_media_type or [ContentType.IMAGE_GEOTIFF]
        ext = get_extension(ctype[0], dot=False)
        path = os.path.join(output_dir, f"map.{ext}")
        with open(path, mode="wb") as file:
            data = cast(io.BytesIO, cov.coverage(col_id)).getbuffer()
            file.write(data)  # type: ignore
        resolved_files.append(path)

    elif col_fmt in ExecuteCollectionFormat.OGC_MAP:
        maps = Maps(
            url=api_url,
            # FIXME: add 'auth' or 'headers'?
        )
        ctype = col_media_type or [ContentType.IMAGE_GEOTIFF]
        ext = get_extension(ctype[0], dot=False)
        path = os.path.join(output_dir, f"map.{ext}")
        with open(path, mode="wb") as file:
            data = cast(io.BytesIO, maps.map(col_id)).getbuffer()
            file.write(data)  # type: ignore
        resolved_files.append(path)

    outputs = {
        "outputs": [{"class": "File", "location": path} for path in resolved_files],
    }
    with open(os.path.join(output_dir, OUTPUT_CWL_JSON), mode="w", encoding="utf-8") as file:
        return json.dump(outputs, file)


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
    sys.exit(process(col_in, proc_in, ns.o))


if __name__ == "__main__":
    main()
