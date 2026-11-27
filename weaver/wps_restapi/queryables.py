"""
Resolution of queryable parameters shared by listing and queryables endpoints of processes and jobs.
"""
from typing import TYPE_CHECKING

import colander
from pyramid.httpexceptions import HTTPBadRequest, HTTPUnprocessableEntity

from weaver.utils import get_request_args
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.colander_extras import OAS3TypeConversionDispatcher
from weaver.wps_restapi.filter import FilterLanguage

if TYPE_CHECKING:
    from typing import Any, Dict

    from weaver.typedefs import AnyRequestType, JSON


def get_queryables_params(request):
    # type: (AnyRequestType) -> Dict[str, str]
    """
    Obtains the request queryable parameters with the ``datetime`` ``+`` offset restored from its decoded space.
    """
    params = dict(get_request_args(request))
    if params.get("datetime", False):
        params["datetime"] = params["datetime"].replace(" ", "+")
    return params


def resolve_queryables_params(params):
    # type: (Dict[str, Any]) -> Dict[str, Any]
    """
    Converts validated queryable query parameters into the arguments supported by the listing search of the stores.

    The deprecated ``sort`` is interpreted as ``sortby``. The ``datetime`` and ``filter`` expressions are parsed.

    :raises HTTPBadRequest: If both ``sort`` and ``sortby`` are provided.
    :raises HTTPUnprocessableEntity: If the ``datetime`` interval is inverted.
    """
    params = dict(params)
    if params.get("sort") and params.get("sortby"):
        raise HTTPBadRequest(json={
            "error": "ListingInvalidParameter",
            "description": "Cannot combine 'sortby' with the deprecated 'sort'.",
            "value": {"sort": params["sort"], "sortby": params["sortby"]},
        })
    sort = params.pop("sort", None)
    if sort:
        params["sortby"] = sort

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


def get_queryables_schema(schema, schema_id):
    # type: (colander.SchemaNode, str) -> JSON
    """
    Describes supported collection parameters using the same schema that validates listing requests.
    """
    queryables = OAS3TypeConversionDispatcher()(schema)
    queryables["$id"] = schema_id
    return queryables
