import logging
from typing import TYPE_CHECKING

import colander
from celery.exceptions import TimeoutError as CeleryTaskTimeoutError
from pyramid.httpexceptions import HTTPAccepted, HTTPBadRequest, HTTPCreated, HTTPNotFound, HTTPOk

from weaver.config import WeaverFeature, get_weaver_configuration
from weaver.database import get_db
from weaver.datatype import Bill, Quote
from weaver.exceptions import ProcessNotFound, QuoteNotFound, log_unhandled_exceptions
from weaver.execute import ExecuteMode
from weaver.formats import OutputFormat
from weaver.owsexceptions import OWSMissingParameterValue
from weaver.processes.types import ProcessType
from weaver.quotation.estimation import process_quote_estimator
from weaver.sort import Sort
from weaver.store.base import StoreBills, StoreProcesses, StoreQuotes
from weaver.utils import as_int, get_header, get_settings, parse_prefer_header_execute_mode
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.processes.processes import submit_local_job

if TYPE_CHECKING:
    from weaver.datatype import Process

LOGGER = logging.getLogger(__name__)


@sd.process_quotes_service.post(tags=[sd.TAG_BILL_QUOTE, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                                schema=sd.PostProcessQuoteRequestEndpoint(), response_schemas=sd.post_quotes_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def request_quote(request):
    """
    Request a quotation for a process.
    """
    settings = get_settings(request)
    weaver_config = get_weaver_configuration(settings)

    if weaver_config not in WeaverFeature.QUOTING:
        raise HTTPBadRequest("Unsupported quoting request for configuration '{}'.".format(weaver_config))

    process_id = request.matchdict.get("process_id")
    process_store = get_db(request).get_store(StoreProcesses)
    try:
        process = process_store.fetch_by_id(process_id)  # type: Process
    except ProcessNotFound:
        raise ProcessNotFound(json={
            "title": "NoSuchProcess",
            "type": "http://www.opengis.net/def/exceptions/ogcapi-processes-1/1.0/no-such-process",
            "detail": "Process with specified reference identifier does not exist.",
            "status": ProcessNotFound.code,
            "cause": str(process_id)
        })

    if (
        (process.type not in [ProcessType.APPLICATION, ProcessType.WORKFLOW]) or
        (process.type == ProcessType.WORKFLOW and weaver_config not in WeaverFeature.REMOTE)
    ):
        raise HTTPBadRequest(json={
            "title": "UnsupportedOperation",
            "detail": f"Unsupported quoting process type '{process.type}' on '{weaver_config}' instance.",
            "status": HTTPBadRequest.code,
            "instance": process.href(settings)
        })

    try:
        process_params = sd.QuoteProcessParametersSchema().deserialize(request.json)
    except colander.Invalid as exc:
        raise OWSMissingParameterValue(json={
            "title": "MissingParameterValue",
            "cause": "Invalid schema: [{!s}]".format(exc.msg),
            "error": exc.__class__.__name__,
            "value": exc.value
        })

    quote_store = get_db(request).get_store(StoreQuotes)
    quote_user = request.authenticated_userid
    quote_info = {
        "process": process_id,
        "processParameters": process_params,
        "user": quote_user
    }
    quote = Quote(**quote_info)
    quote = quote_store.save_quote(quote)
    max_wait = as_int(settings.get("weaver.quote_sync_max_wait"), default=20)
    mode, wait, applied = parse_prefer_header_execute_mode(request.headers, process.jobControlOptions, max_wait)

    result = process_quote_estimator.delay(quote.id)
    LOGGER.debug("Celery pending task [%s] for quote [%s].", result.id, quote.id)
    if mode == ExecuteMode.SYNC and wait:
        LOGGER.debug("Celery task requested as sync if it completes before (wait=%ss)", wait)
        try:
            result.wait(timeout=wait)
        except CeleryTaskTimeoutError:
            pass
        if result.ready():
            quote = quote_store.fetch_by_id(quote.id)
            data = quote.json()
            data.update({"description": sd.CreatedQuoteResponse.description})
            data.update({"links": quote.links(settings)})
            data = sd.CreatedQuoteResponse().deserialize(data)
            return HTTPCreated(json=data)
        else:
            LOGGER.debug("Celery task requested as sync took too long to complete (wait=%ss). Continue in async.", wait)
            # sync not respected, therefore must drop it
            # since both could be provided as alternative preferences, drop only async with limited subset
            prefer = get_header("Preference-Applied", applied, pop=True)
            _, _, async_applied = parse_prefer_header_execute_mode({"Prefer": prefer}, [ExecuteMode.ASYNC])
            applied = async_applied

    data = quote.partial()
    data.update({"description": sd.AcceptedQuoteResponse.description})
    headers = {"Location": quote.href(settings)}
    headers.update(applied)
    return HTTPAccepted(headers=headers, json=data)


@sd.process_quotes_service.get(tags=[sd.TAG_BILL_QUOTE, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                               schema=sd.ProcessQuotesEndpoint(), response_schemas=sd.get_quote_list_responses)
@sd.quotes_service.get(tags=[sd.TAG_BILL_QUOTE], renderer=OutputFormat.JSON,
                       schema=sd.QuotesEndpoint(), response_schemas=sd.get_quote_list_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_quote_list(request):
    """
    Get list of quotes IDs.
    """

    page = int(request.params.get("page", "0"))
    limit = int(request.params.get("limit", "10"))
    filters = {
        "process_id": request.params.get("process", None) or request.matchdict.get("process_id", None),
        "page": page,
        "limit": limit,
        "sort": request.params.get("sort", Sort.CREATED),
    }
    store = get_db(request).get_store(StoreQuotes)
    items, count = store.find_quotes(**filters)
    return HTTPOk(json={
        "count": count,
        "page": page,
        "limit": limit,
        "quotes": [quote.id for quote in items]
    })


@sd.process_quote_service.get(tags=[sd.TAG_BILL_QUOTE, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                              schema=sd.ProcessQuoteEndpoint(), response_schemas=sd.get_quote_responses)
@sd.quote_service.get(tags=[sd.TAG_BILL_QUOTE], renderer=OutputFormat.JSON,
                      schema=sd.QuoteEndpoint(), response_schemas=sd.get_quote_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_quote_info(request):
    """
    Get quote information.
    """
    quote_id = request.matchdict.get("quote_id")
    store = get_db(request).get_store(StoreQuotes)
    try:
        quote = store.fetch_by_id(quote_id)
    except QuoteNotFound:
        raise HTTPNotFound("Could not find quote with specified 'quote_id'.")
    return HTTPOk(json=quote.json())


@sd.process_quote_service.post(tags=[sd.TAG_BILL_QUOTE, sd.TAG_EXECUTE, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                               schema=sd.PostProcessQuote(), response_schemas=sd.post_quote_responses)
@sd.quote_service.post(tags=[sd.TAG_BILL_QUOTE, sd.TAG_EXECUTE], renderer=OutputFormat.JSON,
                       schema=sd.PostQuote(), response_schemas=sd.post_quote_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def execute_quote(request):
    """
    Execute a quoted process.
    """
    quote_info = get_quote_info(request).json["quote"]
    quote_bill_info = {
        "quote": quote_info.get("id"),
        "price": quote_info.get("price"),
        "currency": quote_info.get("currency")
    }
    job_resp = submit_local_job(request)
    job_json = job_resp.json
    job_id = job_json.get("jobID")
    user_id = str(request.authenticated_userid)
    store = get_db(request).get_store(StoreBills)
    bill = store.save_bill(Bill(user=user_id, job=job_id, **quote_bill_info))
    job_json.update({"bill": bill.id})
    return HTTPCreated(json=job_json)
