from twitcher.wps_restapi import swagger_definitions as sd, sort
from twitcher.exceptions import QuoteNotFound, ProcessNotFound
from twitcher.adapter import quotestore_factory, processstore_factory
from twitcher.processes.types import *
from pyramid.httpexceptions import *
import logging
logger = logging.getLogger('TWITCHER')


@sd.process_quotes_service.post(tags=[sd.bill_quote_tag, sd.processes_tag], renderer='json',
                                schema=sd.PostProcessQuoteRequestEndpoint(), response_schemas=sd.post_quotes_responses)
def request_quote(request):
    """
    Request a quotation for a process.
    """
    pass


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
    items, count = store.find_quotes(request, **filters)
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
    quote_id = request.matchdict.get('quote_id')
