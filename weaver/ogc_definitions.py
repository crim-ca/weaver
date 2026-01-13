#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Utilities for handling :term:`OGC API` and :term:`OWS` conformance classes and definitions.
"""

OGC_DEF_CRS_UNDEFINED_URN = "urn:ogc:def:crs:::-1"

OGC_DEF_CRS84_URN = "urn:ogc:def:crs:CRS::84"
OGC_DEF_CRS84_URI = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
OGC_DEF_CRS84H_URI = "http://www.opengis.net/def/crs/OGC/0/CRS84h"

OGC_DEF_BBOX_CRS_EPSG4326_URN = "urn:ogc:def:crs:EPSG::4326"
OGC_DEF_BBOX_CRS_EPSG4326_SHORT = "EPSG:4326"
OGC_DEF_BBOX_FORMAT = "ogc-bbox"  # equal CRS:84 and EPSG:4326, equivalent to WGS84 with swapped lat-lon order

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


def curie(uri: str) -> str:
    """
    Convert a :term:`URI` to its :term:`CURIE` format.
    """
    if uri.startswith("http://www.opengis.net/def/"):
        uri = uri.replace("http://www.opengis.net/def/", "ogc-").replace("/", ":").replace("/0/", ":")
        uri = f"[{uri}]"
    return uri


def normalize(uri: str) -> str:
    """
    Normalize :term:`URI` from various formats, such as :term:`CURIE`, :term:`URN` or HTTP(S).
    """
    if uri.startswith("urn:ogc:def:"):
        uri = uri.replace("urn:ogc:def:", "http://www.opengis.net/def/").replace(":", "/").replace("//", "/0/")
    if uri.startswith("[ogc-") and uri.endswith("]"):
        uri = uri[1:-1].replace(":", "/").replace("ogc-", "http://www.opengis.net/")
    uri = uri.rstrip("/").replace("https://", "http://")
    return uri
