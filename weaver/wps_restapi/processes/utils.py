import logging
import math
from typing import TYPE_CHECKING

import colander
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.request import Request
from pyramid.settings import asbool

from weaver.config import WeaverFeature, get_weaver_configuration
from weaver.database import get_db
from weaver.formats import ContentType
from weaver.store.base import StoreProcesses
from weaver.utils import get_path_kvp, get_settings, get_weaver_url
from weaver.visibility import Visibility
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Dict, List, Optional, Tuple

    from weaver.datatype import Service, Process
    from weaver.typedefs import JSON

LOGGER = logging.getLogger(__name__)


def get_processes_filtered_by_valid_schemas(request):
    # type: (Request) -> Tuple[List[JSON], List[str], Dict[str, Optional[int]], bool, int]
    """
    Validates the processes summary schemas and returns them into valid/invalid lists.

    :returns: List of valid process and invalid processes IDs for manual cleanup, along with filtering parameters.
    """
    settings = get_settings(request)
    with_providers = False
    if get_weaver_configuration(settings) in WeaverFeature.REMOTE:
        with_providers = asbool(request.params.get("providers", False))
    revisions_param = sd.ProcessRevisionsQuery(unknown="ignore").deserialize(request.params)
    with_revisions = revisions_param.get("revisions")
    paging_query = sd.ProcessPagingQuery()
    paging_value = {param.name: param.default for param in paging_query.children}
    paging_names = set(paging_value)
    paging_param = paging_query.deserialize(request.params)
    if with_providers and any(value != paging_value[param] for param, value in paging_param.items()):
        raise HTTPBadRequest(json={
            "description": "Cannot combine paging/sorting parameters with providers full listing query.",
            "error": "ListingInvalidParameter",
            "value": list(paging_names.intersection(request.params))
        })

    store = get_db(request).get_store(StoreProcesses)
    processes, total_local_processes = store.list_processes(
        visibility=Visibility.PUBLIC,
        total=True,
        **revisions_param,
        **paging_param
    )
    valid_processes = []
    invalid_processes_ids = []
    for process in processes:  # type: Process
        try:
            valid_processes.append(process.summary(revision=with_revisions))
        except colander.Invalid as invalid:
            process_ref = process.tag if with_revisions else process.identifier
            LOGGER.debug("Invalid process [%s] because:\n%s", process_ref, invalid)
            invalid_processes_ids.append(process.identifier)
    return valid_processes, invalid_processes_ids, paging_param, with_providers, total_local_processes


def get_process_list_links(request, paging, total, provider=None):
    # type: (Request, Dict[str, int], Optional[int], Optional[Service]) -> List[JSON]
    """
    Obtains a list of all relevant links for the corresponding :term:`Process` listing defined by query parameters.

    :raises IndexError: if the paging values are out of bounds compared to available total :term:`Process`.
    """
    # reapply queries that must be given to obtain the same result in case of subsequent requests (sort, limits, etc.)
    kvp_params = {param: value for param, value in request.params.items() if param != "page"}
    base_url = get_weaver_url(request)
    links = []
    if provider:
        proc_path = sd.provider_processes_service.path.format(provider_id=provider.id)
        links.extend(provider.links(request, self_link="provider"))
    else:
        proc_path = sd.processes_service.path
    proc_url = base_url + proc_path
    links.extend([
        {"href": proc_url, "rel": "collection",
         "type": ContentType.APP_JSON, "title": "Process listing (no filtering queries applied)."},
        {"href": proc_url, "rel": "search",
         "type": ContentType.APP_JSON, "title": "Generic query endpoint to list processes."},
        {"href": proc_url + "?detail=false", "rel": "preview",
         "type": ContentType.APP_JSON, "title": "Process listing summary (identifiers and count only)."},
        {"href": proc_url, "rel": "http://www.opengis.net/def/rel/ogc/1.0/processes",
         "type": ContentType.APP_JSON, "title": "List of registered local processes."},
        {"href": get_path_kvp(proc_url, **request.params), "rel": "self",
         "type": ContentType.APP_JSON, "title": "Current process listing."},
    ])
    if provider:
        prov_url = proc_url.rsplit("/", 1)[0]
        links.append({"href": prov_url, "rel": "up", "type": ContentType.APP_JSON, "title": "Provider description."})
    else:
        links.append({"href": base_url, "rel": "up", "type": ContentType.APP_JSON, "title": "API entrypoint."})

    cur_page = paging.get("page", None)
    per_page = paging.get("limit", None)
    if all(isinstance(num, int) for num in [cur_page, per_page, total]):
        max_page = max(math.ceil(total / per_page) - 1, 0)
        if cur_page < 0 or cur_page > max_page:
            raise IndexError(f"Page index {cur_page} is out of range from [0,{max_page}].")
        links.extend([
            {"href": get_path_kvp(proc_url, page=cur_page, **kvp_params), "rel": "current",
             "type": ContentType.APP_JSON, "title": "Current page of processes query listing."},
            {"href": get_path_kvp(proc_url, page=0, **kvp_params), "rel": "first",
             "type": ContentType.APP_JSON, "title": "First page of processes query listing."},
            {"href": get_path_kvp(proc_url, page=max_page, **kvp_params), "rel": "last",
             "type": ContentType.APP_JSON, "title": "Last page of processes query listing."},
        ])
        if cur_page > 0:
            links.append({
                "href": get_path_kvp(proc_url, page=cur_page - 1, **kvp_params), "rel": "prev",
                "type": ContentType.APP_JSON, "title": "Previous page of processes query listing."
            })
        if cur_page < max_page:
            links.append({
                "href": get_path_kvp(proc_url, page=cur_page + 1, **kvp_params), "rel": "next",
                "type": ContentType.APP_JSON, "title": "Next page of processes query listing."
            })
    return links
