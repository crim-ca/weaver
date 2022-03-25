import functools
import inspect
import logging
from copy import deepcopy
from typing import TYPE_CHECKING

import colander
from pyramid.httpexceptions import HTTPBadRequest, HTTPSuccessful, status_map

from weaver.utils import get_header, get_settings, get_weaver_url
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Any, Callable, Dict, Optional

    from weaver.typedefs import AnySettingsContainer, HeadersType

LOGGER = logging.getLogger(__name__)


class HTTPHeadFileResponse(HTTPSuccessful):
    """
    Provides additional header handing when returning a response to HTTP HEAD request.

    When returning from HTTP HEAD, the body contents are omitted from the response.
    The response **MUST NOT** contain the body contents, but the HTTP headers **SHOULD**
    be identical to the corresponding HTTP GET request.

    .. seealso::
        :rfc:`2616#section-9.4`


    from pyramid.httpexceptions import HTTPException
    .. note::
        Even though no content is provided for HEAD response, ``204`` **SHOULD NOT** be used
        since it must emulate the GET response that would contain the content.

    When setting :attr:`HTTPException.empty_body` on :class:`pyramid.httpexceptions.HTTPException` derived classes,
    :mod:`pyramid` incorrectly drops important headers such as ``Content-Type`` and ``Content-Length`` that should be
    reported as if the file was returned when the represented entity is a file, although no content is actually present.
    When instead the body is omitted (``text=""`` or ``body=b''``), the :meth:`HTTPException.prepare` method also
    incorrectly overrides the ``Content-Type`` and ``Content-Length`` values. Finally, ``Content-Length`` also gets
    recalculated when the content iterator is created from the initialization parameters. This class takes care of all
    these edge cases to properly report content headers of HEAD requests although none is provided.
    """

    def __init__(self, code=200, headers=None, **kwargs):
        # type: (int, Optional[HeadersType], Any) -> None
        # drop any 'app_iter' content generator that would recalculate and reset the content_length
        kwargs.pop("body", None)
        kwargs.pop("json", None)
        kwargs.pop("text", None)
        self.code = code
        http_class = status_map[code]
        self.title = http_class.title
        self.explanation = http_class.explanation
        content_type = None
        if headers:
            # in order to automatically add charset when needed, 'content_type' creates a duplicate
            # remove the original preemptively to avoid errors in parsers receiving the response
            headers = deepcopy(headers)
            content_type = get_header("Content-Type", headers, pop=True)
        super(HTTPHeadFileResponse, self).__init__(
            content_type=content_type,  # don't override content-type
            headerlist=None,    # extend content-type with charset as applicable
            headers=headers,
            app_iter=[b""],  # don't recalculate content-length
            **kwargs
        )

    def prepare(self, environ):
        """
        No contents for HEAD request.
        """


def wps_restapi_base_path(container):
    # type: (AnySettingsContainer) -> str
    settings = get_settings(container)
    restapi_path = settings.get("weaver.wps_restapi_path", "").rstrip("/").strip()
    return restapi_path


def get_wps_restapi_base_url(container):
    # type: (AnySettingsContainer) -> str
    settings = get_settings(container)
    weaver_rest_url = settings.get("weaver.wps_restapi_url")
    if not weaver_rest_url:
        weaver_url = get_weaver_url(settings)
        restapi_path = wps_restapi_base_path(settings)
        weaver_rest_url = weaver_url + restapi_path
    return weaver_rest_url.rstrip("/").strip()


def get_schema_ref(schema, container=None, ref_type="$schema", ref_name=True):
    # type: (colander.SchemaNode, Optional[AnySettingsContainer], str, True) -> Dict[str, str]
    """
    Generates the JSON OpenAPI schema reference relative to the current `Weaver` instance.

    The provided schema should be one of the items listed in ``#/definitions`` of the ``/json`` endpoint.
    No validation is accomplished to avoid long processing of all references.

    If setting ``weaver.schema_url`` is set, this value will be used direct as fully-defined base URL.
    This could be used to refer to a static endpoint where schemas are hosted.
    Otherwise, the current Web Application resolved location is employed with JSON OpenAPI path.

    :param schema: schema-node instance or type for which to generate the OpenAPI reference.
    :param container: application settings to retrieve the base URL of the schema location.
    :param ref_type: key employed to form the reference (e.g.: "$schema", "$ref", "@schema", etc.)
    :param ref_name: indicate if the plain name should also be included under field ``"schema"``.
    :return: OpenAPI schema reference
    """
    is_instance = isinstance(schema, colander.SchemaNode)
    assert is_instance or (inspect.isclass(schema) and issubclass(schema, colander.SchemaNode))
    if is_instance:
        schema = type(schema)
    schema_name = schema.__name__
    settings = get_settings(container)
    weaver_schema_url = settings.get("weaver.schema_url")
    if not weaver_schema_url:
        restapi_path = get_wps_restapi_base_url(container)
        weaver_schema_url = f"{restapi_path}{sd.openapi_json_service.path}#/definitions"
    weaver_schema_url = weaver_schema_url.rstrip("/").strip()
    schema_ref = {ref_type: f"{weaver_schema_url}/{schema_name}"}
    if ref_name:
        schema_ref.update({"schema": schema_name})
    return schema_ref


def handle_schema_validation(schema=None):
    # type: (Optional[colander.SchemaNode]) -> Callable
    """
    Convert a schema validation error into an HTTP error with error details about the failure.

    :param schema: If provided, document this schema as the reference of the failed schema validation.
    :raises HTTPBadRequest: If any schema validation error occurs when handling the decorated function.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapped(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except colander.Invalid as ex:
                data = {
                    "type": "InvalidSchema",
                    "detail": "Invalid value failed schema validation.",
                    "error": colander.Invalid.__name__,
                    "cause": ex.asdict(),
                    "value": ex.value,
                }
                if schema:
                    data.update({
                        "schema": get_schema_ref(schema)
                    })
                raise HTTPBadRequest(json=data)
        return wrapped
    return decorator
