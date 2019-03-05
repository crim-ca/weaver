from weaver.config import get_weaver_configuration, WEAVER_CONFIGURATION_EMS, WEAVER_CONFIGURATION_ADES
from weaver.database import get_db
from weaver.exceptions import QuoteNotFound, ProcessNotFound
from weaver.datatype import Bill, Quote
from weaver.processes.types import PROCESS_APPLICATION, PROCESS_WORKFLOW
from weaver.processes.wps_package import get_process_location, get_package_workflow_steps
from weaver.store.base import StoreBills, StoreQuotes
from weaver.utils import get_weaver_url
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.processes.processes import submit_local_job
from weaver import sort
from pyramid.httpexceptions import (
    HTTPOk,
    HTTPCreated,
    HTTPBadRequest,
    HTTPNotFound,
)
from datetime import timedelta
from duration import to_iso8601
import logging
import random

logger = logging.getLogger('weaver')


# noinspection PyUnusedLocal
def process_quote_estimator(process):
    """
    :param process: instance of :class:`weaver.datatype.Process` for which to evaluate the quote.
    :return: dict of {price, currency, estimatedTime} values for the process quote.
    """
    # TODO: replace by some fancy ml technique or something?
    price = random.uniform(0, 10)
    currency = 'CAD'
    estimated_time = to_iso8601(timedelta(minutes=random.uniform(5, 60)))
    return {'price': price, 'currency': currency, 'estimatedTime': estimated_time}


@sd.process_quotes_service.post(tags=[sd.bill_quote_tag, sd.processes_tag], renderer='json',
                                schema=sd.PostProcessQuoteRequestEndpoint(), response_schemas=sd.post_quotes_responses)
def request_quote(request):
    """
    Request a quotation for a process.
    """
    settings = request.registry.settings
    weaver_config = get_weaver_configuration(settings)

    if weaver_config not in [WEAVER_CONFIGURATION_ADES, WEAVER_CONFIGURATION_EMS]:
        raise HTTPBadRequest("Unsupported request for configuration `{}`.".format(weaver_config))

    process_id = request.matchdict.get('process_id')
    process_store = get_db(request).get_store('processes')
    try:
        process = process_store.fetch_by_id(process_id, request=request)
    except ProcessNotFound:
        raise HTTPNotFound("Could not find process with specified `process_id`.")

    store = get_db(request).get_store(StoreQuotes)
    process_url = get_process_location(process_id, data_source=get_weaver_url(request.registry.settings))
    process_type = process.type
    process_params = dict()
    for param in ['inputs', 'outputs', 'mode', 'response']:
        if param in request.json:
            process_params[param] = request.json.pop(param)
    process_quote_info = process_quote_estimator(process)
    process_quote_info.update({
        'process': process_id,
        'processParameters': process_params,
        'location': process_url,
        'user': str(request.authenticated_userid)
    })

    # loop workflow sub-process steps to get individual quotes
    if process_type == PROCESS_WORKFLOW and weaver_config == WEAVER_CONFIGURATION_EMS:
        workflow_quotes = list()

        for step in get_package_workflow_steps(process_url):
            # retrieve quote from provider ADES
            # TODO: data source mapping
            process_step_url = get_process_location(step['reference'])
            process_quote_url = '{}/quotations'.format(process_step_url)
            subreq = request.copy()
            subreq.path_info = process_quote_url
            resp_json = request.invoke_subrequest(subreq).json()
            quote_json = resp_json['quote']
            quote = store.save_quote(Quote(**quote_json))
            workflow_quotes.append(quote.id)

        process_quote_info.update({'steps': workflow_quotes})
        quote = store.save_quote(Quote(**process_quote_info))
        return HTTPCreated(json={"quote": quote.json()})

    # single application quotes (ADES or EMS)
    elif process_type == PROCESS_APPLICATION:
        quote = store.save_quote(Quote(**process_quote_info))
        quote_json = quote.json()
        quote_json.pop('steps', None)
        return HTTPCreated(json={"quote": quote_json})

    # error if not handled up to this point
    raise HTTPBadRequest("Unsupported quoting process type `{0}` on `{1}`.".format(process_type, weaver_config))


@sd.process_quotes_service.get(tags=[sd.bill_quote_tag, sd.processes_tag], renderer='json',
                               schema=sd.ProcessQuotesEndpoint(), response_schemas=sd.get_quote_list_responses)
@sd.quotes_service.get(tags=[sd.bill_quote_tag], renderer='json',
                       schema=sd.QuotesEndpoint(), response_schemas=sd.get_quote_list_responses)
def get_quote_list(request):
    """
    Get list of quotes IDs.
    """

    page = int(request.params.get('page', '0'))
    limit = int(request.params.get('limit', '10'))
    filters = {
        'process_id': request.params.get('process', None) or request.matchdict.get('process_id', None),
        'page': page,
        'limit': limit,
        'sort': request.params.get('sort', sort.SORT_CREATED),
    }
    store = get_db(request).get_store(StoreQuotes)
    items, count = store.find_quotes(**filters)
    return HTTPOk(json={
        'count': count,
        'page': page,
        'limit': limit,
        'quotes': [quote.id for quote in items]
    })


@sd.process_quote_service.get(tags=[sd.bill_quote_tag, sd.processes_tag], renderer='json',
                              schema=sd.ProcessQuoteEndpoint(), response_schemas=sd.get_quote_responses)
@sd.quote_service.get(tags=[sd.bill_quote_tag], renderer='json',
                      schema=sd.QuoteEndpoint(), response_schemas=sd.get_quote_responses)
def get_quote_info(request):
    """
    Get quote information.
    """
    quote_id = request.matchdict.get('quote_id')
    store = get_db(request).get_store(StoreQuotes)
    try:
        quote = store.fetch_by_id(quote_id)
    except QuoteNotFound:
        raise HTTPNotFound("Could not find quote with specified `quote_id`.")
    return HTTPOk(json={'quote': quote.json()})


@sd.process_quote_service.post(tags=[sd.bill_quote_tag, sd.execute_tag, sd.processes_tag], renderer='json',
                               schema=sd.PostProcessQuote(), response_schemas=sd.post_quote_responses)
@sd.quote_service.post(tags=[sd.bill_quote_tag, sd.execute_tag], renderer='json',
                       schema=sd.PostQuote(), response_schemas=sd.post_quote_responses)
def execute_quote(request):
    """
    Execute a quoted process.
    """
    quote_info = get_quote_info(request).json['quote']
    quote_bill_info = {
        'quote': quote_info.get('id'),
        'price': quote_info.get('price'),
        'currency': quote_info.get('currency')
    }
    job_resp = submit_local_job(request)
    job_json = job_resp.json
    job_id = job_json.get('jobID')
    user_id = str(request.authenticated_userid)
    store = get_db(request).get_store(StoreBills)
    bill = store.save_bill(Bill(user=user_id, job=job_id, **quote_bill_info))
    job_json.update({"bill": bill.id})
    return HTTPCreated(json=job_json)
