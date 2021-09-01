import inspect
import logging
from typing import TYPE_CHECKING

from colander import SchemaNode

from weaver.utils import get_settings, get_weaver_url
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Dict

    from weaver.typedefs import AnySettingsContainer

LOGGER = logging.getLogger(__name__)


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


def get_schema_ref(schema, container, ref_type="$schema", ref_name=True):
    # type: (SchemaNode, AnySettingsContainer, str, True) -> Dict[str, str]
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
    is_instance = isinstance(schema, SchemaNode)
    assert is_instance or (inspect.isclass(schema) and issubclass(schema, SchemaNode))
    if is_instance:
        schema = type(schema)
    schema_name = schema.__name__
    settings = get_settings(container)
    weaver_schema_url = settings.get("weaver.schema_url")
    if not weaver_schema_url:
        restapi_path = get_wps_restapi_base_url(container)
        weaver_schema_url = "{}{}#/definitions".format(restapi_path, sd.openapi_json_service.path)
    weaver_schema_url = weaver_schema_url.rstrip("/").strip()
    schema_ref = {ref_type: "{}/{}".format(weaver_schema_url, schema_name)}
    if ref_name:
        schema_ref.update({"schema": schema_name})
    return schema_ref
