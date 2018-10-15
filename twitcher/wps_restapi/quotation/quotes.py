from twitcher.wps_restapi import swagger_definitions as sd
from twitcher import sort
from twitcher.wps_restapi.processes.processes import submit_local_job
from twitcher.config import get_twitcher_configuration, TWITCHER_CONFIGURATION_EMS, TWITCHER_CONFIGURATION_ADES
from twitcher.exceptions import QuoteNotFound, ProcessNotFound
from twitcher.adapter import billstore_factory, quotestore_factory, processstore_factory
from twitcher.datatype import Bill, Quote
from twitcher.processes.types import *
from twitcher.processes.wps_package import get_process_location, get_package_workflow_steps
from twitcher.utils import get_twitcher_url
from pyramid.httpexceptions import *
from pyramid.security import authenticated_userid
from datetime import timedelta
from duration import to_iso8601
import logging
import random

logger = logging.getLogger('TWITCHER')


def process_quote_estimator(process):
    """
    :param process: instance of :class:`twitcher.datatype.Process` for which to evaluate the quote.
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
    twitcher_config = get_twitcher_configuration(settings)

    if twitcher_config not in [TWITCHER_CONFIGURATION_ADES, TWITCHER_CONFIGURATION_EMS]:
        raise HTTPBadRequest("Unsupported request for configuration `{}`.".format(twitcher_config))

    process_id = request.matchdict.get('process_id')
    process_store = processstore_factory(request.registry)
    try:
        process = process_store.fetch_by_id(process_id, request=request)
    except ProcessNotFound:
        raise HTTPNotFound("Could not find process with specified `process_id`.")

    process_type = process.type
    store = quotestore_factory(request.registry)
    process_url = get_process_location(process_id, data_source=get_twitcher_url(request.registry.settings))
    process_quote_info = process_quote_estimator(process)
    user_id = str(authenticated_userid(request))

    # loop workflow sub-process steps to get individual quotes
    if process_type == PROCESS_WORKFLOW and twitcher_config == TWITCHER_CONFIGURATION_EMS:
        workflow_quotes = list()

        for step in get_package_workflow_steps(process_url):
            # retrieve quote from provider ADES
            # TODO: data source mapping
            from twitcher.processes.sources import CRIM_ADES
            process_step_url = get_process_location(step['reference'], data_source=CRIM_ADES)
            process_quote_url = '{}/quotations'.format(process_step_url)
            subreq = request.copy()
            subreq.path_info = process_quote_url
            resp_json = request.invoke_subrequest(subreq).json()
            quote_json = resp_json['quote']
            quote = store.save_quote(Quote(process=quote_json.pop('process'),
                                           price=quote_json.pop('price'),
                                           currency=process_quote_info.get('currency'),
                                           location=process_step_url,
                                           user=user_id))
            workflow_quotes.append(quote.id)
        quote = store.save_quote(Quote(process=process.identifier,
                                       location=process_url,
                                       steps=workflow_quotes,
                                       user=user_id,
                                       **process_quote_info))
        return HTTPCreated(json={"quote": quote.json()})

    # single application quotes (ADES or EMS)
    elif process_type == PROCESS_APPLICATION:
        quote = store.save_quote(Quote(process=process_id, location=process_url, user=user_id, **process_quote_info))
        quote_json = quote.json()
        quote_json.pop('steps', None)
        return HTTPCreated(json={"quote": quote_json})

    # error if not handled up to this point
    raise HTTPBadRequest("Unsupported quoting process type `{0}` on `{1}`.".format(process_type, twitcher_config))


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
    store = quotestore_factory(request.registry)
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
    store = quotestore_factory(request.registry)
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
    quote = get_quote_info(request)
    job_resp = submit_local_job(request)
    job_json = job_resp.json()
    job_id = job_json.get('jobID')
    user_id = request.authenticated_userid
    store = billstore_factory(request.registry)
    bill = store.save_bill(Bill(user=user_id, quote=quote.id, job=job_id, price=quote.price, currency=quote.currency))
    job_json.update({"bill": bill.id})
    return HTTPCreated(json=job_json)
