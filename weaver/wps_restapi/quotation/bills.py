import logging

from pyramid.httpexceptions import HTTPNotFound, HTTPOk

from weaver.database import get_db
from weaver.exceptions import BillNotFound, log_unhandled_exceptions
from weaver.formats import OUTPUT_FORMAT_JSON
from weaver.store.base import StoreBills
from weaver.wps_restapi import swagger_definitions as sd

LOGGER = logging.getLogger(__name__)


@sd.bills_service.get(tags=[sd.TAG_BILL_QUOTE], renderer=OUTPUT_FORMAT_JSON,
                      schema=sd.BillsEndpoint(), response_schemas=sd.get_bill_list_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_bill_list(request):
    """
    Get list of bills IDs.
    """
    store = get_db(request).get_store(StoreBills)
    bills = store.list_bills()
    return HTTPOk(json={"bills": [b.id for b in bills]})


@sd.bill_service.get(tags=[sd.TAG_BILL_QUOTE], renderer=OUTPUT_FORMAT_JSON,
                     schema=sd.BillEndpoint(), response_schemas=sd.get_bill_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_bill_info(request):
    """
    Get bill information.
    """
    bill_id = request.matchdict.get("bill_id")
    store = get_db(request).get_store(StoreBills)
    try:
        bill = store.fetch_by_id(bill_id)
    except BillNotFound:
        raise HTTPNotFound("Could not find bill with specified 'bill_id'.")
    return HTTPOk(json={"bill": bill.json()})
