import logging
from typing import TYPE_CHECKING

import colander
from celery.exceptions import TimeoutError as CeleryTaskTimeoutError
from pyramid.httpexceptions import HTTPAccepted, HTTPCreated, HTTPOk, HTTPPaymentRequired, HTTPUnprocessableEntity
from pyramid.settings import asbool

from weaver.config import WeaverFeature, get_weaver_configuration
from weaver.database import get_db
from weaver.datatype import Bill, Quote
from weaver.exceptions import log_unhandled_exceptions
from weaver.execute import ExecuteMode
from weaver.formats import OutputFormat
from weaver.owsexceptions import OWSInvalidParameterValue
from weaver.processes.execution import validate_process_io
from weaver.processes.utils import get_process
from weaver.processes.types import ProcessType
from weaver.quotation.estimation import (
    execute_quote_estimator,
    get_currency,
    get_quote_estimator_config,
    validate_quote_estimator_config
)
from weaver.sort import Sort
from weaver.store.base import StoreBills, StoreProcesses, StoreQuotes
from weaver.utils import as_int, get_header, get_settings, parse_prefer_header_execute_mode
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.processes.processes import submit_local_job
from weaver.wps_restapi.quotation.utils import get_quote

if TYPE_CHECKING:
    from weaver.typedefs import AnyViewResponse, PyramidRequest

LOGGER = logging.getLogger(__name__)


@sd.process_quotes_service.post(tags=[sd.TAG_BILL_QUOTE, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                                schema=sd.PostProcessQuoteRequestEndpoint(), response_schemas=sd.post_quotes_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def request_quote(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Request a quotation for a process.
    """
    settings = get_settings(request)
    weaver_config = get_weaver_configuration(settings)
    process = get_process(request=request, settings=settings)
    if (
        (process.type not in [ProcessType.APPLICATION, ProcessType.WORKFLOW]) or
        (process.type == ProcessType.WORKFLOW and weaver_config not in WeaverFeature.REMOTE)
    ):
        raise HTTPUnprocessableEntity(json={
            "title": "UnsupportedOperation",
            "detail": f"Unsupported quotation for process type '{process.type}' on '{weaver_config}' instance.",
            "status": HTTPUnprocessableEntity.code,
            "instance": process.href(settings)
        })
    if not get_quote_estimator_config(process, ignore_error=True):
        raise HTTPUnprocessableEntity(json={
            "title": "UnsupportedOperation",
            "detail": (
                f"Unsupported quotation for process '{process.id}'. "
                "It does not provide an estimator configuration."
            ),
            "status": HTTPUnprocessableEntity.code,
            "instance": process.href(settings)
        })

    try:
        process_params = sd.QuoteProcessParametersSchema().deserialize(request.json)
    except colander.Invalid as exc:
        raise OWSInvalidParameterValue(json={
            "title": "InvalidParameterValue",
            "cause": f"Invalid schema: [{exc.msg!s}]",
            "error": exc.__class__.__name__,
            "value": exc.value
        })
    validate_process_io(process, process_params)

    quote_store = get_db(request).get_store(StoreQuotes)
    quote_user = request.authenticated_userid  # FIXME: consider other methods to provide the user
    quote_currency = get_currency(request)
    quote_info = {
        "process": process.id,
        "processParameters": process_params,
        "user": quote_user,
        "currency": quote_currency,  # requested currency until evaluated, overridden if exchange rate not resolvable
    }
    quote = Quote(**quote_info)
    quote = quote_store.save_quote(quote)
    quote_max_wait = settings.get("weaver.quotation_sync_max_wait", settings.get("weaver.quote_sync_max_wait"))
    quote_max_wait = as_int(quote_max_wait, default=20)
    mode, wait, applied = parse_prefer_header_execute_mode(request.headers, process.jobControlOptions, quote_max_wait)

    result = execute_quote_estimator.delay(quote.id)
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


@sd.process_estimator_service.get(tags=[sd.TAG_BILL_QUOTE, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                                  schema=sd.ProcessQuoteEstimatorGetEndpoint(),
                                  response_schemas=sd.get_process_quote_estimator_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_process_quote_estimator(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Get the process quote estimator configuration.
    """
    process = get_process(request=request)
    estimator_config = get_quote_estimator_config(process)
    return HTTPOk(json=estimator_config)


@sd.process_estimator_service.put(tags=[sd.TAG_BILL_QUOTE, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                                  schema=sd.ProcessQuoteEstimatorPutEndpoint(),
                                  response_schemas=sd.put_process_quote_estimator_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def update_process_quote_estimator(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Replace the process quote estimator configuration.
    """
    estimator_config = validate_quote_estimator_config(request.json)
    store = get_db(request).get_store(StoreProcesses)
    process = get_process(request=request, store=store)
    store.set_estimator(process, estimator_config)
    return HTTPOk(json={"description": "Process quote estimator updated."})


@sd.process_estimator_service.delete(tags=[sd.TAG_BILL_QUOTE, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                                     schema=sd.ProcessQuoteEstimatorDeleteEndpoint(),
                                     response_schemas=sd.delete_process_quote_estimator_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def delete_process_quote_estimator(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Reset the process quote estimator configuration to the default values.
    """
    store = get_db(request).get_store(StoreProcesses)
    process = get_process(request=request, store=store)
    store.set_estimator(process, {})
    return HTTPOk(json={"description": "Process quote estimator deleted. Defaults will be used."})


@sd.process_quotes_service.get(tags=[sd.TAG_BILL_QUOTE, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                               schema=sd.ProcessQuotesEndpoint(), response_schemas=sd.get_quote_list_responses)
@sd.quotes_service.get(tags=[sd.TAG_BILL_QUOTE], renderer=OutputFormat.JSON,
                       schema=sd.QuotesEndpoint(), response_schemas=sd.get_quote_list_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_quote_list(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Get list of quotes IDs.
    """

    page = int(request.params.get("page", "0"))
    limit = int(request.params.get("limit", "10"))
    detail = asbool(request.params.get("detail", False))
    filters = {
        "process_id": request.params.get("process", None) or request.matchdict.get("process_id", None),
        "page": page,
        "limit": limit,
        "sort": request.params.get("sort", Sort.CREATED),
    }
    store = get_db(request).get_store(StoreQuotes)
    items, total = store.find_quotes(**filters)
    quotes = [quote.partial() if detail else quote.id for quote in items]
    data = {
        "page": page,
        "limit": limit,
        "count": len(quotes),
        "total": total,
        "quotations": quotes
    }
    body = sd.QuotationListSchema().deserialize(data)
    return HTTPOk(json=body)


@sd.process_quote_service.get(tags=[sd.TAG_BILL_QUOTE, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                              schema=sd.ProcessQuoteEndpoint(), response_schemas=sd.get_quote_responses)
@sd.quote_service.get(tags=[sd.TAG_BILL_QUOTE], renderer=OutputFormat.JSON,
                      schema=sd.QuoteEndpoint(), response_schemas=sd.get_quote_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_quote_info(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Get quote information.
    """
    quote = get_quote(request)
    return HTTPOk(json=quote.json())


@sd.process_quote_service.post(tags=[sd.TAG_BILL_QUOTE, sd.TAG_EXECUTE, sd.TAG_PROCESSES], renderer=OutputFormat.JSON,
                               schema=sd.PostProcessQuote(), response_schemas=sd.post_quote_responses)
@sd.quote_service.post(tags=[sd.TAG_BILL_QUOTE, sd.TAG_EXECUTE], renderer=OutputFormat.JSON,
                       schema=sd.PostQuote(), response_schemas=sd.post_quote_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def execute_quote(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Execute a quoted process.
    """
    quote = get_quote(request)
    if not quote.paid:
        raise HTTPPaymentRequired(json={
            "title": "Payment Required",
            "detail": sd.QuotePaymentRequiredResponse.description,
            "status": HTTPPaymentRequired.code,
            "value": str(quote.id),
        })

    quote_bill_info = {
        "quote": quote.id,
        "price": quote.price,
    }
    job_resp = submit_local_job(request)
    job_json = job_resp.json
    job_id = job_json.get("jobID")
    user_id = str(request.authenticated_userid)
    store = get_db(request).get_store(StoreBills)
    bill = store.save_bill(Bill(user=user_id, job=job_id, **quote_bill_info))
    job_json.update({
        "billID": bill.id,
        "quoteID": quote.id,
    })
    data = sd.CreatedQuoteExecuteResponse().deserialize(job_json)
    return HTTPCreated(json=data)
