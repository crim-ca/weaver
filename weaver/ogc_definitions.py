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
    parts = uri.rsplit("/", 2)
    if len(parts) > 1 and parts[-2] != version:
        uri = f"{parts[0]}/{version}/{parts[2]}"
    return uri


OGC_DEF_CRS_UNDEFINED_URN = "urn:ogc:def:crs:::-1"

# equivalent forms of EPSG:4326, 2D or 3D
OGC_DEF_CRS_WSG84_SHORT = "WGS84"
OGC_DEF_CRS_CRS84_LEGACY_SHORT = "CRS:84"
OGC_DEF_CRS_CRS84_LEGACY_URN = "urn:ogc:def:crs:CRS::84"
OGC_DEF_CRS_CRS84_LEGACY_URI = "http://www.opengis.net/def/crs/CRS/0/84"
OGC_DEF_CRS_CRS84_URN = "urn:ogc:def:crs:OGC:2:84"
OGC_DEF_CRS_CRS84_URI = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
OGC_DEF_CRS_CRS84H_URI = "http://www.opengis.net/def/crs/OGC/0/CRS84h"
OGC_DEF_CRS_OGC_CRS84_SHORT = "OGC:CRS84"
OGC_DEF_CRS_OGC_CRS84_URN = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
OGC_DEF_CRS_EPSG4326_URN = "urn:ogc:def:crs:EPSG::4326"
OGC_DEF_CRS_EPSG4326_SHORT = "EPSG:4326"
OGC_DEF_CRS_EPSG4326_URI = "http://www.opengis.net/def/crs/EPSG/0/4326"
OGC_DEF_CRS_ANY_EPSG4326 = [
    OGC_DEF_CRS_WSG84_SHORT,
    OGC_DEF_CRS_CRS84_LEGACY_SHORT,
    OGC_DEF_CRS_CRS84_LEGACY_URN,
    OGC_DEF_CRS_CRS84_LEGACY_URI,
    OGC_DEF_CRS_CRS84_URN,
    OGC_DEF_CRS_OGC_CRS84_SHORT,
    OGC_DEF_CRS_OGC_CRS84_URN,
    normalize(OGC_DEF_CRS_CRS84_URI, secure=True, version="1.3"),
    normalize(OGC_DEF_CRS_CRS84_URI, secure=False, version="1.3"),
    normalize(OGC_DEF_CRS_CRS84_URI, secure=True, version="0"),
    normalize(OGC_DEF_CRS_CRS84_URI, secure=False, version="0"),
    normalize(OGC_DEF_CRS_CRS84H_URI, secure=False),
    normalize(OGC_DEF_CRS_CRS84H_URI, secure=True),
    OGC_DEF_CRS_EPSG4326_URN,
    OGC_DEF_CRS_EPSG4326_SHORT,
    normalize(OGC_DEF_CRS_EPSG4326_URI, secure=True),
    normalize(OGC_DEF_CRS_EPSG4326_URI, secure=False),
]
