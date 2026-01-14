#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Utilities for handling :term:`OGC API` and :term:`OWS` conformance classes and definitions.
"""
from functools import cache
from typing import Optional


@cache
def curie(uri: str) -> str:
    """
    Convert a :term:`URI` to its :term:`CURIE` format.
    """
    if uri.startswith("http://www.opengis.net/def/"):
        uri = uri.replace("http://www.opengis.net/def/", "")
        parts = uri.split("/")
        ns = parts[1].lower()
        typ = parts[0]
        name = "-".join(parts[3:])
        uri = f"[{ns}-{typ}:{name}]"
        uri = uri.replace("/", ":").replace("-0-", ":")
    return uri


@cache
def normalize(uri: str, version: Optional[str] = None, secure: bool = False) -> str:
    """
    Normalize :term:`URI` from various formats, such as :term:`CURIE`, :term:`URN` or HTTP(S).

    Version ``0`` is considered an alias for any version in the OGC definitions.
    However, link relations and profiles use ``1.0`` instead.
    For :term:`OGC API` conformance classes, they depend on the actual release as applicable.
    The default is applied accordingly if ``None``.

    .. seealso::
        See `opengeospatial/NamingAuthority#120 <https://github.com/opengeospatial/NamingAuthority/issues/120>`_
        for more details.
    """
    if version is None:
        version = "1.0" if any(part in uri for part in ["/rel/", "/profile/", "ogc-rel:", "ogc-profile:"]) else "0"
    if uri.startswith("urn:ogc:def:"):
        uri = uri.replace(":", "/").replace("//", f"/{version}/").replace("urn/ogc/def/", "http://www.opengis.net/def/")
    if uri.startswith("[ogc-") and uri.endswith("]"):
        uri = uri[1:-1].replace(":", f"/ogc/{version}/").replace("ogc-", "http://www.opengis.net/def/")
    uri = uri.rstrip("/")
    uri = uri.replace("http://", "https://") if secure else uri.replace("https://", "http://")
    return uri


OGC_DEF_CRS_UNDEFINED_URN = "urn:ogc:def:crs:::-1"

# equivalent forms of EPSG:4326, 2D or 3D
OGC_DEF_CRS_WSG84_SHORT = "WGS84"
OGC_DEF_CRS_CRS84_URN_LEGACY = "urn:ogc:def:crs:CRS::84"
OGC_DEF_CRS_CRS84_URN = "urn:ogc:def:crs:OGC:2:84"
OGC_DEF_CRS_CRS84_URI = "http://www.opengis.net/def/crs/OGC/0/CRS84"
OGC_DEF_CRS_CRS84H_URI = "http://www.opengis.net/def/crs/OGC/0/CRS84h"
OGC_DEF_CRS_EPSG4326_URN = "urn:ogc:def:crs:EPSG::4326"
OGC_DEF_CRS_EPSG4326_SHORT = "EPSG:4326"
OGC_DEF_CRS_EPSG4326_URI = "http://www.opengis.net/def/crs/EPSG/0/4326"
OGC_DEF_CRS_ANY_EPSG4326 = [
    OGC_DEF_CRS_WSG84_SHORT,
    OGC_DEF_CRS_CRS84_URN_LEGACY,
    OGC_DEF_CRS_CRS84_URN,
    normalize(OGC_DEF_CRS_CRS84_URI, secure=True, version="1.3"),
    normalize(OGC_DEF_CRS_CRS84_URI, secure=False, version="1.3"),
    normalize(OGC_DEF_CRS_CRS84_URI, secure=True, version="0"),
    normalize(OGC_DEF_CRS_CRS84_URI, secure=False, version="0"),
    OGC_DEF_CRS_EPSG4326_URN,
    OGC_DEF_CRS_EPSG4326_SHORT,
    normalize(OGC_DEF_CRS_EPSG4326_URI, secure=True, version="0"),
    normalize(OGC_DEF_CRS_EPSG4326_URI, secure=False, version="0"),
]

OGC_DEF_BBOX_FORMAT = "ogc-bbox"  # equal CRS:84 and EPSG:4326, equivalent to WGS84 with swapped lat-lon order
OGC_DEF_BBOX_CRS_EPSG4326_URN = OGC_DEF_CRS_EPSG4326_URN

OGC_API_PROC_REL_EXCEPTIONS_URI = "http://www.opengis.net/def/rel/ogc/1.0/exceptions"
OGC_API_PROC_REL_EXECUTE_URI = "http://www.opengis.net/def/rel/ogc/1.0/execute"
OGC_API_PROC_REL_PROCESSES_URI = "http://www.opengis.net/def/rel/ogc/1.0/processes"
OGC_API_PROC_REL_PROCESS_DESC_URI = "http://www.opengis.net/def/rel/ogc/1.0/process-desc"
OGC_API_PROC_REL_JOB_RESULTS_URI = "http://www.opengis.net/def/rel/ogc/1.0/results"
OGC_DEF_PROC_REL_JOB_LIST_URI = "http://www.opengis.net/def/rel/ogc/1.0/job-list"
OGC_API_PROC_REL_JOB_LOG_URI = "http://www.opengis.net/def/rel/ogc/1.0/log"

OGC_API_PROC_PROFILE_PROC_DESC_URI = "http://www.opengis.net/def/profile/OGC/0/ogc-process-description"
OGC_API_PROC_PROFILE_PROC_LIST_URI = "http://www.opengis.net/def/profile/OGC/0/ogc-process-list"
OGC_API_PROC_PROFILE_EXECUTE_URI = "http://www.opengis.net/def/profile/OGC/0/ogc-execute-request"
OGC_API_PROC_PROFILE_RESULTS_URI = "http://www.opengis.net/def/profile/OGC/0/ogc-results"
OGC_API_PROC_PROFILE_JOB_DESC_URI = "http://www.opengis.net/def/profile/OGC/0/job-description"
OGC_API_PROC_PROFILE_JOB_LIST_URI = "http://www.opengis.net/def/profile/OGC/0/jobs-list"

OGC_API_PROC_PROFILE_DOCKER_APP_URI = "http://www.opengis.net/profiles/eoc/dockerizedApplication"
OGC_API_PROC_PROFILE_WPS_APP_URI = "http://www.opengis.net/profiles/eoc/wpsApplication"
