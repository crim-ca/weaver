"""
Resolution of OGC API - Records catalog parameters shared by listing, queryables and sortables of processes and jobs.
"""
from typing import TYPE_CHECKING

import colander
from pyramid.httpexceptions import HTTPBadRequest, HTTPUnprocessableEntity
from pyramid.response import Response

from weaver.formats import ContentType
from weaver.sort import Sort
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.colander_extras import OAS3TypeConversionDispatcher
from weaver.wps_restapi.filter import FilterLanguage
from weaver.wps_restapi.utils import get_wps_restapi_base_url

if TYPE_CHECKING:
    from typing import Any, Dict

    from cornice import Service

    from weaver.typedefs import AnyViewResponse, JSON, PyramidRequest


def resolve_queryables_params(params):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    """
    Converts validated queryable query parameters into the arguments supported by the listing search of the stores.

    The ``datetime`` and ``filter`` expressions are parsed.

    :raises HTTPUnprocessableEntity: If the ``datetime`` interval is inverted.
    """
    params = dict(params)

    filter_expr = params.pop("filter", None)
    filter_lang = params.pop("filter-lang", None)
    params.pop("filter-crs", None)
    if filter_expr:
        default_lang = FilterLanguage.CQL2_TEXT if isinstance(filter_expr, str) else FilterLanguage.CQL2_JSON
        filter_lang = filter_lang or default_lang
        try:
            params["filter_ast"] = sd.FilterSchema().validate(filter_expr, filter_lang)
        except colander.Invalid as exc:
            raise HTTPBadRequest(json={
                "error": "ListingInvalidParameter",
                "description": f"Invalid 'filter' expression: {exc.msg}",
                "value": {"filter": filter_expr, "filter-lang": filter_lang},
            })

    datetime_value = params.pop("datetime", None)
    if datetime_value:
        dti = sd.datetime_interval_parser(datetime_value)
        if dti.get("before", False) and dti.get("after", False) and dti["after"] > dti["before"]:
            raise HTTPUnprocessableEntity(json={
                "code": "InvalidDateFormat",
                "description": "Datetime at the start of the interval must be less than the datetime at the end."
            })
        params["datetime_interval"] = dti
    return params


def schema_response(body):
    # type: (JSON) -> AnyViewResponse
    """
    Provides the JSON Schema body using the media-type indicated by :term:`OGC API - Records`.
    """
    return Response(json_body=body, content_type=ContentType.APP_SCHEMA_JSON)


def get_queryables_schema(request, schema):
    # type: (PyramidRequest, colander.SchemaNode) -> AnyViewResponse
    """
    Describes supported catalog parameters using the same schema that validates listing requests.
    """
    queryables = OAS3TypeConversionDispatcher()(schema)
    queryables["$id"] = request.path_url
    return schema_response(queryables)


def get_sortables_schema(request, schema):
    # type: (PyramidRequest, sd.SortByArray) -> AnyViewResponse
    """
    Describes supported catalog sorting fields using the enum values that validate the ``sortby`` parameter.
    """
    fields = sorted({field.lstrip("+-") for field in schema.children[0].validator.choices})
    properties = {}
    for field in fields:
        properties[field] = {"title": field, "type": "string"}
        if field in [Sort.CREATED, Sort.FINISHED]:
            properties[field]["format"] = "date-time"
    return schema_response({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": request.path_url,
        "type": "object",
        "properties": properties,
    })


def get_catalog_links(request, rel, services):
    # type: (PyramidRequest, str, Dict[str, Service]) -> JSON
    """
    Provides links to the queryables or sortables endpoint of each catalog, named by their respective key.
    """
    base_url = get_wps_restapi_base_url(request)
    links = [{"href": request.path_url, "rel": "self", "type": ContentType.APP_JSON, "title": "Current endpoint."}]
    for name, service in services.items():
        links.append({
            "href": base_url + service.path, "rel": rel, "type": ContentType.APP_SCHEMA_JSON,
            "title": f"Supported {name} {rel.rsplit('/', 1)[-1]}.",
        })
    return {"links": links}
