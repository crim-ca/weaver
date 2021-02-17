:mod:`weaver.wps_restapi.api`
=============================

.. py:module:: weaver.wps_restapi.api


Module Contents
---------------

.. data:: LOGGER
   

   

.. function:: api_frontpage(request)

   Frontpage of weaver.


.. function:: api_versions(request: Request) -> HTTPException

   Weaver versions information.


.. function:: api_conformance(request: Request) -> HTTPException

   Weaver specification conformance information.


.. function:: get_swagger_json(http_scheme: str = 'http', http_host: str = 'localhost', base_url: Optional[str] = None, use_docstring_summary: bool = True) -> JSON

   Obtains the JSON schema of weaver API from request and response views schemas.

   :param http_scheme: Protocol scheme to use for building the API base if not provided by base URL parameter.
   :param http_host: Hostname to use for building the API base if not provided by base URL parameter.
   :param base_url: Explicit base URL to employ of as API base instead of HTTP scheme/host parameters.
   :param use_docstring_summary:
       Setting that controls if function docstring should be used to auto-generate the summary field of responses.

   .. seealso::
       - :mod:`weaver.wps_restapi.swagger_definitions`


.. function:: api_swagger_json(request: Request) -> dict

   weaver REST API schema generation in JSON format.


.. function:: api_swagger_ui(request)

   weaver REST API swagger-ui schema documentation (this page).


.. function:: get_request_info(request: Request, detail: Optional[str] = None) -> JSON

   Provided additional response details based on the request and execution stack on failure.


.. function:: ows_json_format(function)

   Decorator that adds additional detail in the response's JSON body if this is the returned content-type.


.. function:: not_found_or_method_not_allowed(request)

   Overrides the default is HTTPNotFound [404] by appropriate HTTPMethodNotAllowed [405] when applicable.

   Not found response can correspond to underlying process operation not finding a required item, or a completely
   unknown route (path did not match any existing API definition).
   Method not allowed is more specific to the case where the path matches an existing API route, but the specific
   request method (GET, POST, etc.) is not allowed on this path.

   Without this fix, both situations return [404] regardless.


.. function:: unauthorized_or_forbidden(request)

   Overrides the default is HTTPForbidden [403] by appropriate HTTPUnauthorized [401] when applicable.

   Unauthorized response is for restricted user access according to credentials and/or authorization headers.
   Forbidden response is for operation refused by the underlying process operations.

   Without this fix, both situations return [403] regardless.

   .. seealso::
       http://www.restapitutorial.com/httpstatuscodes.html


