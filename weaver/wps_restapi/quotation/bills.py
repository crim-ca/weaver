import logging
from typing import TYPE_CHECKING

from pyramid.httpexceptions import HTTPNotFound, HTTPOk

from weaver.database import get_db
from weaver.exceptions import BillNotFound, log_unhandled_exceptions
from weaver.formats import ContentType, OutputFormat
from weaver.store.base import StoreBills
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from pyramid.config import Configurator

    from weaver.typedefs import AnyViewResponse, PyramidRequest

LOGGER = logging.getLogger(__name__)


@sd.bills_service.get(
    tags=[sd.TAG_BILL_QUOTE],
    schema=sd.BillsEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_bill_list_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_bill_list(request):
    # type: (PyramidRequest) -> AnyViewResponse
    """
    Get list of bills IDs.
    """
    store = get_db(request).get_store(StoreBills)
    bills = store.list_bills()
    return HTTPOk(json={"bills": [b.id for b in bills]})


@sd.bill_service.get(
    tags=[sd.TAG_BILL_QUOTE],
    schema=sd.BillEndpoint(),
    accept=ContentType.APP_JSON,
    renderer=OutputFormat.JSON,
    response_schemas=sd.get_bill_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_bill_info(request):
    # type: (PyramidRequest) -> AnyViewResponse
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


def includeme(config):
    # type: (Configurator) -> None
    LOGGER.info("Adding WPS REST API bill views...")
    config.add_cornice_service(sd.bills_service)
    config.add_cornice_service(sd.bill_service)
