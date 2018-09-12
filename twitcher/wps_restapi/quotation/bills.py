from twitcher.wps_restapi import swagger_definitions as sd
import logging
logger = logging.getLogger('TWITCHER')


@sd.bills_service.get(tags=[sd.bill_quote_tag], renderer='json',
                      schema=sd.BillsEndpoint(), response_schemas=sd.get_bill_list_responses)
def get_bill_list(request):
    """
    Get list of bills IDs.
    """
    pass


@sd.bill_service.get(tags=[sd.bill_quote_tag], renderer='json',
                     schema=sd.BillEndpoint(), response_schemas=sd.get_bill_responses)
def get_bill_info(request):
    """
    Get bill information.
    """
    pass
