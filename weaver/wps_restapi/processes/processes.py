import logging
from typing import TYPE_CHECKING

import colander
from box import Box
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPException,
    HTTPForbidden,
    HTTPNotFound,
    HTTPOk,
    HTTPServiceUnavailable,
    HTTPUnprocessableEntity
)
from pyramid.response import Response
from pyramid.settings import asbool

from weaver.database import get_db
from weaver.exceptions import ProcessNotFound, ServiceException, log_unhandled_exceptions
from weaver.formats import (
    ContentType,
    OutputFormat,
    add_content_type_charset,
    clean_media_type_format,
    guess_target_format,
    repr_json
)
from weaver.processes import opensearch
from weaver.processes.constants import ProcessSchema
from weaver.processes.execution import submit_job, submit_job_dispatch_wps
from weaver.processes.utils import deploy_process_from_payload, get_process, update_process_metadata
from weaver.status import Status
from weaver.store.base import StoreJobs, StoreProcesses
from weaver.utils import clean_json_text_body, fully_qualified_name, get_any_id, get_header, make_link_header
from weaver.visibility import Visibility
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.processes.utils import get_process_list_links, get_processes_filtered_by_valid_schemas
from weaver.wps_restapi.providers.utils import get_provider_services

if TYPE_CHECKING:
    from pyramid.config import Configurator

    from weaver.typedefs import AnyViewResponse, JSON, PyramidRequest

LOGGER = logging.getLogger(__name__)


@sd.processes_service.get(
    tags=[sd.TAG_PROCESSES, sd.TAG_GETCAPABILITIES],
    schema=sd.GetProcessesEndpoint(),
    accept=ContentType.TEXT_HTML,
    renderer="weaver.wps_restapi:templates/responses/process_listing.mako",
    response_schemas=sd.derive_responses(
        sd.get_processes_responses,
        sd.GenericHTMLResponse(name="HTMLProcessListing", description="Listing of processes.")
    ),
)
@sd.processes_service.get(
    tags=[sd.TAG_PROCESSES, sd.TAG_GETCAPABILITIES],
    schema=sd.GetProcessesEndpoint(),
    accept=ContentType.TEXT_XML,
    response_schemas=sd.get_processes_responses,
)
@sd.processes_service.get(
    tags=[sd.TAG_PROCESSES, sd.TAG_GETCAPABILITIES],
    schema=sd.GetProcessesEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_processes_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_processes(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    List registered processes (GetCapabilities).

    Optionally list both local and provider processes.
    """
    try:
        params = sd.GetProcessesQuery().deserialize(request.params)
    except colander.Invalid as ex:
        raise HTTPBadRequest(json={
            "code": "ProcessInvalidParameter",
            "description": "Process query parameters failed validation.",
            "error": colander.Invalid.__name__,
            "cause": str(ex),
            "value": repr_json(ex.value or dict(request.params), force_string=False),
        })

    links = asbool(params.get("links", True))
    detail = asbool(params.get("detail", True))
    ignore = asbool(params.get("ignore", True))
    if request.accept == ContentType.TEXT_HTML:
        detail = ignore = True
    try:
        # get local processes and filter according to schema validity
        # (previously deployed process schemas can become invalid because of modified schema definitions
        results = get_processes_filtered_by_valid_schemas(request, detail=detail, links=links)
        processes, invalid_processes, paging, with_providers, total_processes = results
        if invalid_processes:
            raise HTTPServiceUnavailable(
                "Previously deployed processes are causing invalid schema integrity errors. "
                f"Manual cleanup of following processes is required: {invalid_processes}"
            )

        body = {"processes": processes if detail else [get_any_id(p) for p in processes]}  # type: JSON
        if not with_providers:
            paging = {  # remove other params
                "page": paging.get("page"),
                "limit": paging.get("limit"),
                "count": len(processes),
            }
            body.update(paging)
        else:
            paging = {}  # disable to remove paging-related links

        try:
            body["links"] = get_process_list_links(request, paging, total_processes)
        except IndexError as exc:
            raise HTTPBadRequest(json={
                "description": str(exc),
                "cause": "Invalid paging parameters.",
                "error": type(exc).__name__,
                "value": repr_json(paging, force_string=False)
            })

        # if 'EMS/HYBRID' and '?providers=True', also fetch each provider's processes
        if with_providers:
            # param 'check' enforced because must fetch for listing of available processes (GetCapabilities)
            # when 'ignore' is not enabled, any failing definition should raise any derived 'ServiceException'
            services = get_provider_services(request, ignore=ignore, check=True)
            body.update({
                "providers": [svc.summary(request, ignore=ignore) if detail else {"id": svc.name} for svc in services]
            })
            invalid_services = [False] * len(services)
            for i, provider in enumerate(services):
                # ignore failing parsing of the service description
                if body["providers"][i] is None:
                    invalid_services[i] = True
                    continue
                # attempt parsing available processes and ignore again failing items
                processes = provider.processes(request, ignore=ignore)
                if processes is None:
                    invalid_services[i] = True
                    continue
                total_processes += len(processes)
                body["providers"][i].update({
                    "processes": processes if detail else [get_any_id(proc) for proc in processes]
                })
            if any(invalid_services):
                LOGGER.debug("Invalid providers dropped due to failing parsing and ignore query: %s",
                             [svc.name for svc, status in zip(services, invalid_services) if status])
                body["providers"] = [svc for svc, ignore in zip(body["providers"], invalid_services) if not ignore]

        body["total"] = total_processes
        body["description"] = sd.OkGetProcessesListResponse.description
        LOGGER.debug("Process listing generated, validating schema...")
        body = sd.MultiProcessesListing().deserialize(body)
        request.response.headers.extend([
            ("Link", make_link_header(link))
            for link in body["links"]
        ])
        return Box(body)

    except ServiceException as exc:
        LOGGER.debug("Error when listing provider processes using query parameter raised: [%s]", exc, exc_info=exc)
        raise HTTPServiceUnavailable(json={
            "description": "At least one provider could not list its processes. "
                           "Failing provider errors were requested to not be ignored.",
            "exception": fully_qualified_name(exc),
            "error": str(exc)
        })
    except HTTPException:
        raise
    except colander.Invalid as exc:
        raise HTTPBadRequest(json={
            "type": "InvalidParameterValue",
            "title": "Invalid parameter value.",
            "description": "Submitted request parameters are invalid or could not be processed.",
            "cause": clean_json_text_body(f"Invalid schema: [{exc.msg or exc!s}]"),
            "error": exc.__class__.__name__,
            "value": repr_json(exc.value, force_string=False),
        })


@sd.processes_service.post(
    tags=[sd.TAG_PROCESSES, sd.TAG_DEPLOY],
    schema=sd.PostProcessesEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.post_processes_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def add_local_process(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Register a local process.
    """
    return deploy_process_from_payload(request.text, request)  # use text to allow parsing as JSON or YAML


@sd.process_service.put(
    tags=[sd.TAG_PROCESSES, sd.TAG_DEPLOY],
    schema=sd.PutProcessEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.put_process_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def put_local_process(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Update a registered local process with a new definition.

    Updates the new process MAJOR semantic version from the previous one if not specified explicitly.
    For MINOR or PATCH changes to metadata of the process definition, consider using the PATCH request.
    """
    process = get_process(request=request, revision=False)  # ignore tagged version since must always be latest
    return deploy_process_from_payload(request.text, request, overwrite=process)


@sd.process_service.patch(
    tags=[sd.TAG_PROCESSES, sd.TAG_DEPLOY],
    schema=sd.PatchProcessEndpoint(),
    renderer=OutputFormat.JSON,
    response_schemas=sd.patch_process_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def patch_local_process(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Update metadata of a registered local process.

    Updates the new process MINOR or PATCH semantic version if not specified explicitly, based on updated contents.
    Changes that impact only metadata such as description or keywords imply PATCH update.
    Changes to properties that might impact process operation such as supported formats implies MINOR update.
    Changes that completely redefine the process require a MAJOR update using PUT request.
    """
    return update_process_metadata(request)


@sd.process_service.get(
    tags=[sd.TAG_PROCESSES, sd.TAG_DESCRIBEPROCESS],
    schema=sd.ProcessEndpoint(),
    accept=ContentType.TEXT_HTML,
    renderer="weaver.wps_restapi:templates/responses/process_description.mako",
    response_schemas=sd.derive_responses(
        sd.get_process_responses,
        sd.GenericHTMLResponse(name="HTMLProcessDescription", description="Process description.")
    ),
)
@sd.process_service.get(
    tags=[sd.TAG_PROCESSES, sd.TAG_DESCRIBEPROCESS],
    schema=sd.ProcessEndpoint(),
    accept=ContentType.ANY_XML,
    response_schemas=sd.get_process_responses,
)
@sd.process_service.get(
    tags=[sd.TAG_PROCESSES, sd.TAG_DESCRIBEPROCESS],
    schema=sd.ProcessEndpoint(),
    accept=ContentType.APP_YAML,
    response_schemas=sd.get_process_responses,
)
@sd.process_service.get(
    tags=[sd.TAG_PROCESSES, sd.TAG_DESCRIBEPROCESS],
    schema=sd.ProcessEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_process_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_local_process(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Get a registered local process information (DescribeProcess).
    """
    try:
        process = get_process(request=request)
        process["inputs"] = opensearch.replace_inputs_describe_process(process.inputs, process.payload)
        schema = request.params.get("schema")
        ctype = guess_target_format(request)
        ctype_json = add_content_type_charset(ContentType.APP_JSON, "UTF-8")
        ctype_yaml = add_content_type_charset(ContentType.APP_YAML, "UTF-8")
        ctype_html = add_content_type_charset(ContentType.TEXT_HTML, "UTF-8")
        ctype_xml = add_content_type_charset(ContentType.APP_XML, "UTF-8")
        proc_url = process.href(request)
        if ctype in ContentType.ANY_XML or str(schema).upper() == ProcessSchema.WPS:
            offering = process.offering(ProcessSchema.WPS, request=request)
            headers = [
                ("Link", make_link_header(f"{proc_url}?f=json", rel="alternate", type=ctype_json)),
                ("Link", make_link_header(f"{proc_url}?f=html", rel="alternate", type=ctype_html)),
                ("Link", make_link_header(f"{proc_url}?f=yaml", rel="alternate", type=ctype_yaml)),
                ("Content-Type", ctype_xml),
            ]
            return Response(offering, headerlist=headers)
        elif ctype == ContentType.APP_YAML:
            offering = process.offering(schema)
            content = OutputFormat.convert(offering, OutputFormat.YAML)
            headers = [
                ("Link", make_link_header(f"{proc_url}?f=json", rel="alternate", type=ctype_json)),
                ("Link", make_link_header(f"{proc_url}?f=html", rel="alternate", type=ctype_html)),
                ("Link", make_link_header(f"{proc_url}?f=xml", rel="alternate", type=ctype_xml)),
                ("Link", make_link_header(sd.OGC_API_PROC_PROFILE_PROC_DESC_URL, rel="profile")),
                ("Content-Profile", sd.OGC_API_PROC_PROFILE_PROC_DESC_URL),
                ("Content-Type", ctype_yaml),
            ]
            return HTTPOk(headers=headers, content_type=ctype, charset="utf-8", body=content)
        elif ctype == ContentType.APP_JSON:
            offering = process.offering(schema)
            request.response.content_type = ctype_json
            request.response.headers.extend([
                ("Link", make_link_header(f"{proc_url}?f=xml", rel="alternate", type=ctype_xml)),
                ("Link", make_link_header(f"{proc_url}?f=yaml", rel="alternate", type=ctype_yaml)),
                ("Link", make_link_header(f"{proc_url}?f=html", rel="alternate", type=ctype_html)),
                ("Link", make_link_header(sd.OGC_API_PROC_PROFILE_PROC_DESC_URL, rel="profile")),
                ("Content-Profile", sd.OGC_API_PROC_PROFILE_PROC_DESC_URL),
            ])
            return Box(offering)
        else:  # HTML
            offering = process.offering(schema)
            request.response.headers.extend([
                ("Link", make_link_header(f"{proc_url}?f=json", rel="alternate", type=ctype_json)),
                ("Link", make_link_header(f"{proc_url}?f=yaml", rel="alternate", type=ctype_yaml)),
                ("Link", make_link_header(f"{proc_url}?f=xml", rel="alternate", type=ctype_xml)),
            ])
            return Box(offering)
    # FIXME: handle colander invalid directly in tween (https://github.com/crim-ca/weaver/issues/112)
    except colander.Invalid as ex:
        raise HTTPBadRequest(f"Invalid schema: [{ex!s}]\nValue: [{ex.value!s}]")


@sd.process_package_service.get(
    tags=[sd.TAG_PROCESSES, sd.TAG_DESCRIBEPROCESS],
    schema=sd.ProcessPackageEndpoint(),
    accept=[
        ContentType.APP_JSON,
        ContentType.APP_YAML,
        ContentType.APP_CWL,
        ContentType.APP_CWL_JSON,
        ContentType.APP_CWL_YAML,
        ContentType.APP_CWL_X,
    ],
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_process_package_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_local_process_package(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Get a registered local process package definition.
    """
    process = get_process(request=request)
    content_type = get_header("Accept", request.headers, default=ContentType.APP_CWL_JSON)
    # ignore default browser request injecting HTML
    # ignore 'weaver.wps_restapi_html_override_user_agent' as well since HTML cannot apply here
    if all(ctype in content_type for ctype in [ContentType.TEXT_HTML, ContentType.ANY]):
        content_type = ContentType.APP_CWL_JSON
    headers = {
        "Link": make_link_header(sd.CWL_SCHEMA_URL, rel="profile", type=ContentType.APP_YAML),
        "Content-Schema": sd.CWL_SCHEMA_URL,
        "Content-Profile": sd.CWL_SCHEMA_URL,
    }
    yml_fmt = [ContentType.APP_YAML, ContentType.APP_CWL_YAML]
    cwl_fmt = OutputFormat.YAML if any(ctype in content_type for ctype in yml_fmt) else OutputFormat.JSON
    package = OutputFormat.convert(process.package, cwl_fmt)
    content = {"json": package} if cwl_fmt == OutputFormat.JSON else {"body": package}
    content = content if package else {}
    return HTTPOk(headers=headers, content_type=content_type, charset="utf-8", **content)


@sd.process_payload_service.get(
    tags=[sd.TAG_PROCESSES, sd.TAG_DESCRIBEPROCESS],
    schema=sd.ProcessPayloadEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_process_payload_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_local_process_payload(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Get a registered local process payload definition.
    """
    process = get_process(request=request)
    return HTTPOk(json=process.payload or {})


@sd.process_visibility_service.get(
    tags=[sd.TAG_PROCESSES, sd.TAG_VISIBILITY],
    schema=sd.ProcessVisibilityGetEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_process_visibility_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_process_visibility(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Get the visibility of a registered local process.
    """
    process = get_process(request=request)
    return HTTPOk(json={"value": process.visibility})


@sd.process_visibility_service.put(
    tags=[sd.TAG_PROCESSES, sd.TAG_VISIBILITY],
    content_type=ContentType.APP_JSON,
    schema=sd.ProcessVisibilityPutEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.put_process_visibility_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def set_process_visibility(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Set the visibility of a registered local process.
    """
    visibility = Visibility.get(request.json.get("value"))
    process_id = request.matchdict.get("process_id")
    if not isinstance(process_id, str):
        raise HTTPUnprocessableEntity("Invalid process identifier.")
    if visibility not in Visibility:
        raise HTTPBadRequest(f"Invalid visibility value specified: {visibility!s}")

    try:
        store = get_db(request).get_store(StoreProcesses)
        process = store.fetch_by_id(process_id)
        if not process.mutable:
            raise HTTPForbidden(json={
                "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-2/1.0/immutable-process",
                "title": "Process immutable.",
                "detail": "Cannot change the visibility of builtin process.",
                "status": HTTPForbidden.code,
                "cause": {"mutable": False}
            })
        store.set_visibility(process_id, visibility)
        return HTTPOk(json={"value": visibility})
    except TypeError:
        raise HTTPBadRequest("Value of visibility must be a string.")
    except ValueError:
        raise HTTPUnprocessableEntity(f"Value of visibility must be one of : {Visibility.values()!s}")
    except ProcessNotFound as ex:
        raise HTTPNotFound(str(ex))


@sd.process_service.delete(
    tags=[sd.TAG_PROCESSES, sd.TAG_DEPLOY],
    schema=sd.ProcessEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.delete_process_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def delete_local_process(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Unregister a local process.
    """
    db = get_db(request)
    proc_store = db.get_store(StoreProcesses)
    process = get_process(request=request)
    process_id = process.id
    if not process.mutable:
        raise HTTPForbidden(json={
            "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-2/1.0/immutable-process",
            "title": "Process immutable.",
            "detail": "Cannot delete an immutable process.",
            "status": HTTPForbidden.code,
            "cause": {"mutable": False}
        })
    job_store = db.get_store(StoreJobs)
    jobs, total = job_store.find_jobs(process=process_id, status=Status.RUNNING, page=None, limit=None)
    if total != 0:
        raise HTTPForbidden(json={
            "title": "ProcessBusy",
            "type": "ProcessBusy",
            "detail": "Process with specified identifier is in use by at least one job and cannot be undeployed.",
            "status": HTTPForbidden.code,
            "cause": {"jobs": [str(job.id) for job in jobs]}
        })
    if proc_store.delete_process(process_id, visibility=Visibility.PUBLIC):
        return HTTPOk(json={
            "description": sd.OkDeleteProcessResponse.description,
            "identifier": process_id,
            "undeploymentDone": True,
        })
    LOGGER.error("Existing process [%s] should have been deleted with success status.", process_id)
    raise HTTPForbidden("Deletion of process has been refused by the database or could not have been validated.")


@sd.process_execution_service.post(
    tags=[sd.TAG_PROCESSES, sd.TAG_EXECUTE, sd.TAG_JOBS],
    content_type=list(ContentType.ANY_XML),
    schema=sd.PostProcessJobsEndpointXML(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.post_process_jobs_responses,
)
@sd.process_execution_service.post(
    tags=[sd.TAG_PROCESSES, sd.TAG_EXECUTE, sd.TAG_JOBS],
    content_type=ContentType.APP_JSON,
    schema=sd.PostProcessJobsEndpointJSON(),
    # accept=ContentType.APP_JSON,  # allow anything for single-output or multipart combinations, validated downstream
    renderer=OutputFormat.JSON,
    response_schemas=sd.post_process_jobs_responses,
)
@sd.process_jobs_service.post(
    tags=[sd.TAG_PROCESSES, sd.TAG_EXECUTE, sd.TAG_JOBS],
    content_type=list(ContentType.ANY_XML),
    schema=sd.PostProcessJobsEndpointXML(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.post_process_jobs_responses,
)
@sd.process_jobs_service.post(
    tags=[sd.TAG_PROCESSES, sd.TAG_EXECUTE, sd.TAG_JOBS],
    content_type=ContentType.APP_JSON,
    schema=sd.PostProcessJobsEndpointJSON(),
    # accept=ContentType.APP_JSON,  # allow anything for single-output or multipart combinations, validated downstream
    renderer=OutputFormat.JSON,
    response_schemas=sd.post_process_jobs_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def submit_local_job(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Execute a process registered locally.

    Execution location and method is according to deployed Application Package.
    """
    process = get_process(request=request)
    ctype = get_header("Content-Type", request.headers, default=None)
    ctype = clean_media_type_format(ctype, strip_parameters=True)
    if ctype in ContentType.ANY_XML:
        return submit_job_dispatch_wps(request, process)
    return submit_job(request, process, tags=["wps-rest", "ogc-api"])


def includeme(config):
    # type: (Configurator) -> None
    LOGGER.info("Adding WPS REST API processes views...")
    config.add_cornice_service(sd.processes_service)
    config.add_cornice_service(sd.process_service)
    config.add_cornice_service(sd.process_package_service)
    config.add_cornice_service(sd.process_payload_service)
    config.add_cornice_service(sd.process_visibility_service)
    # added within jobs (conflict)
    # config.add_cornice_service(sd.process_jobs_service)
    # config.add_cornice_service(sd.jobs_full_service)
    config.add_cornice_service(sd.process_execution_service)
