import copy

import logging
from typing import TYPE_CHECKING

import colander
from pyramid.httpexceptions import (
    HTTPBadRequest,
    HTTPConflict,
    HTTPException,
    HTTPForbidden,
    HTTPNotFound,
    HTTPOk,
    HTTPServiceUnavailable,
    HTTPUnprocessableEntity
)
from pyramid.settings import asbool

from weaver.database import get_db
from weaver.exceptions import ProcessNotFound, ServiceException, log_unhandled_exceptions
from weaver.formats import OutputFormat, repr_json
from weaver.processes import opensearch
from weaver.processes.execution import submit_job
from weaver.processes.utils import deploy_process_from_payload, get_process
from weaver.status import Status
from weaver.store.base import StoreJobs, StoreProcesses
from weaver.utils import VersionLevel, as_version_major_minor_patch, fully_qualified_name, get_any_id, is_update_version
from weaver.visibility import Visibility
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.processes.utils import get_process_list_links, get_processes_filtered_by_valid_schemas
from weaver.wps_restapi.providers.utils import get_provider_services
from weaver.wps_restapi.utils import parse_content

if TYPE_CHECKING:
    from weaver.typedefs import JSON, AnyViewResponse, PyramidRequest

LOGGER = logging.getLogger(__name__)


@sd.processes_service.get(schema=sd.GetProcessesEndpoint(), tags=[sd.TAG_PROCESSES, sd.TAG_GETCAPABILITIES],
                          response_schemas=sd.get_processes_responses)
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

    detail = asbool(params.get("detail", True))
    ignore = asbool(params.get("ignore", True))
    try:
        # get local processes and filter according to schema validity
        # (previously deployed process schemas can become invalid because of modified schema definitions
        results = get_processes_filtered_by_valid_schemas(request)
        processes, invalid_processes, paging, with_providers, total_processes = results
        if invalid_processes:
            raise HTTPServiceUnavailable(
                "Previously deployed processes are causing invalid schema integrity errors. "
                f"Manual cleanup of following processes is required: {invalid_processes}"
            )

        body = {"processes": processes if detail else [get_any_id(p) for p in processes]}  # type: JSON
        if not with_providers:
            paging = {"page": paging.get("page"), "limit": paging.get("limit")}  # remove other params
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
        return HTTPOk(json=body)

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
    # FIXME: handle colander invalid directly in tween (https://github.com/crim-ca/weaver/issues/112)
    except colander.Invalid as ex:
        raise HTTPBadRequest(f"Invalid schema: [{ex!s}]")


@sd.processes_service.post(tags=[sd.TAG_PROCESSES, sd.TAG_DEPLOY], renderer=OutputFormat.JSON,
                           schema=sd.PostProcessesEndpoint(), response_schemas=sd.post_processes_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def add_local_process(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Register a local process.
    """
    return deploy_process_from_payload(request.text, request)  # use text to allow parsing as JSON or YAML


@sd.process_service.patch(tags=[sd.TAG_PROCESSES, sd.TAG_DEPLOY], renderer=OutputFormat.JSON,
                          schema=sd.PatchProcessEndpoint(), response_schemas=sd.patch_process_responses)
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
    data = parse_content(request, content_schema=sd.PatchProcessBodySchema)
    store = get_db(request).get_store(StoreProcesses)
    process = get_process(request=request, store=store)  # latest if only 'processId', or specific version if using tag
    if not process.mutable:
        raise HTTPForbidden(json={
            "title": "Process immutable.",
            "type": "ProcessImmutable",
            "detail": "Cannot update an immutable process.",
            "status": HTTPForbidden.code,
            "cause": {"mutable": False}
        })

    # apply requested changes for update
    # (see 'PatchProcessBodySchema' for specific handling based on unspecified/null/empty-list)
    description = data.get("description")
    keywords = data.get("keywords")
    metadata = data.get("metadata")
    links = data.get("links")
    update_level = VersionLevel.PATCH  # metadata only
    try:
        any_update = False
        if description is not None:
            any_update = True
            process.description = description
        if isinstance(keywords, list):
            any_update = True
            if not len(keywords):
                process.keywords = []
            else:
                keys = copy.deepcopy(process.keywords)
                keys.extend(keywords)
                process.keywords = keys
        if isinstance(metadata, list):
            any_update = True
            if not len(metadata):
                process.metadata = []
            else:
                meta = copy.deepcopy(process.metadata)
                meta.extend(metadata)
                process.metadata = meta
        if isinstance(links, list):
            any_update = True
            if not len(links):
                process.additional_links = []
            else:
                x_links = copy.deepcopy(process.additional_links)
                x_links.extend(links)
                process.additional_links = x_links
        if not any_update:
            raise colander.Invalid(None, msg="No parameters provided for update.")
    except colander.Invalid as exc:
        raise HTTPBadRequest(json={
            "code": "ProcessInvalidParameter",
            "description": "Process update parameters failed validation.",
            "error": colander.Invalid.__name__,
            "cause": str(exc),
            "value": repr_json(exc.value, force_string=False),
        })

    # employ user provided version or bump to next PATCH version from selected process
    # must be tested in both cases against available versions since selected process is not necessarily the latest
    version = data.get("version")
    old_version = process.version
    if not version:
        new_version = as_version_major_minor_patch(old_version)
        if update_level == VersionLevel.PATCH:
            new_version[2] += 1  # bump PATCH
        elif update_level == VersionLevel.MINOR:
            new_version[1] += 1  # bump MINOR
    else:
        new_version = as_version_major_minor_patch(version)
    # version must be within available range against selected process for needed update level
    process_versions = store.find_versions(process.id)
    if not is_update_version(new_version, process_versions, update_level):
        raise HTTPUnprocessableEntity()
    process.version = new_version

    try:
        old_process = store.update_version(process.id, old_version)
        new_process = store.save_process(process)
    except ProcessNotFound:
        pass
    else:
        raise HTTPConflict()


    return HTTPOk()


@sd.process_service.put(tags=[sd.TAG_PROCESSES, sd.TAG_DEPLOY], renderer=OutputFormat.JSON,
                        schema=sd.PostProcessesEndpoint(), response_schemas=sd.patch_process_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def put_local_process(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Update a registered local process with a new definition.

    Updates the new process MAJOR semantic version from the previous one if not specified explicitly.
    For MINOR or PATCH changes to metadata definitions, consider using the PATCH request.
    """
    data = parse_content(request, content_schema=sd.PutProcessBodySchema)
    store = get_db(request).get_store(StoreProcesses)
    process = get_process(request=request, store=store)
    return HTTPOk()


@sd.process_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_DESCRIBEPROCESS], renderer=OutputFormat.JSON,
                        schema=sd.ProcessEndpoint(), response_schemas=sd.get_process_responses)
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
        offering = process.offering(schema)
        return HTTPOk(json=offering)
    # FIXME: handle colander invalid directly in tween (https://github.com/crim-ca/weaver/issues/112)
    except colander.Invalid as ex:
        raise HTTPBadRequest(f"Invalid schema: [{ex!s}]\nValue: [{ex.value!s}]")


@sd.process_package_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_DESCRIBEPROCESS], renderer=OutputFormat.JSON,
                                schema=sd.ProcessPackageEndpoint(), response_schemas=sd.get_process_package_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_local_process_package(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Get a registered local process package definition.
    """
    process = get_process(request=request)
    return HTTPOk(json=process.package or {})


@sd.process_payload_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_DESCRIBEPROCESS], renderer=OutputFormat.JSON,
                                schema=sd.ProcessPayloadEndpoint(), response_schemas=sd.get_process_payload_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_local_process_payload(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Get a registered local process payload definition.
    """
    process = get_process(request=request)
    return HTTPOk(json=process.payload or {})


@sd.process_visibility_service.get(tags=[sd.TAG_PROCESSES, sd.TAG_VISIBILITY], renderer=OutputFormat.JSON,
                                   schema=sd.ProcessVisibilityGetEndpoint(),
                                   response_schemas=sd.get_process_visibility_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_process_visibility(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Get the visibility of a registered local process.
    """
    process = get_process(request=request)
    return HTTPOk(json={u"value": process.visibility})


@sd.process_visibility_service.put(tags=[sd.TAG_PROCESSES, sd.TAG_VISIBILITY], renderer=OutputFormat.JSON,
                                   schema=sd.ProcessVisibilityPutEndpoint(),
                                   response_schemas=sd.put_process_visibility_responses)
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
            raise HTTPForbidden("Cannot change the visibility of builtin process.")
        store.set_visibility(process_id, visibility)
        return HTTPOk(json={u"value": visibility})
    except TypeError:
        raise HTTPBadRequest("Value of visibility must be a string.")
    except ValueError:
        raise HTTPUnprocessableEntity(f"Value of visibility must be one of : {Visibility.values()!s}")
    except ProcessNotFound as ex:
        raise HTTPNotFound(str(ex))


@sd.process_service.delete(tags=[sd.TAG_PROCESSES, sd.TAG_DEPLOY], renderer=OutputFormat.JSON,
                           schema=sd.ProcessEndpoint(), response_schemas=sd.delete_process_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def delete_local_process(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Unregister a local process.
    """
    db = get_db(request)
    proc_store = db.get_store(StoreProcesses)
    process = get_process(request=request, store=proc_store)
    process_id = process.id
    if not process.mutable:
        raise HTTPForbidden(json={
            "title": "Process immutable.",
            "type": "ProcessImmutable",
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
            "detail": "Process with specified identifier is in use by a least one job and cannot be undeployed.",
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


@sd.process_execution_service.post(tags=[sd.TAG_PROCESSES, sd.TAG_EXECUTE, sd.TAG_JOBS], renderer=OutputFormat.JSON,
                                   schema=sd.PostProcessJobsEndpoint(), response_schemas=sd.post_process_jobs_responses)
@sd.process_jobs_service.post(tags=[sd.TAG_PROCESSES, sd.TAG_EXECUTE, sd.TAG_JOBS], renderer=OutputFormat.JSON,
                              schema=sd.PostProcessJobsEndpoint(), response_schemas=sd.post_process_jobs_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def submit_local_job(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Execute a process registered locally.

    Execution location and method is according to deployed Application Package.
    """
    process = get_process(request=request)
    return submit_job(request, process, tags=["wps-rest"])
