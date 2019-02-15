from weaver.wps_restapi import swagger_definitions as sd
from weaver.adapter import billstore_factory
from weaver.exceptions import BillNotFound
from pyramid.httpexceptions import *
import logging
logger = logging.getLogger('weaver')


@sd.bills_service.get(tags=[sd.bill_quote_tag], renderer='json',
                      schema=sd.BillsEndpoint(), response_schemas=sd.get_bill_list_responses)
def get_bill_list(request):
    """
    Get list of bills IDs.
    """
    store = billstore_factory(request.registry)
    bills = store.list_bills()
    return HTTPOk(json={'bills': [b.id for b in bills]})


@sd.bill_service.get(tags=[sd.bill_quote_tag], renderer='json',
                     schema=sd.BillEndpoint(), response_schemas=sd.get_bill_responses)
def get_bill_info(request):
    """
    Get bill information.
    """
    bill_id = request.matchdict.get('bill_id')
    store = billstore_factory(request.registry)
    try:
        bill = store.fetch_by_id(bill_id)
    except BillNotFound:
        raise HTTPNotFound('Could not find bill with specified `bill_id`.')
    return HTTPOk(json={'bill': bill.json()})
