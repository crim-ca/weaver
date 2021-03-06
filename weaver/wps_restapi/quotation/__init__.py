import logging

from weaver.formats import OUTPUT_FORMAT_JSON
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.quotation import bills as b, quotes as q

LOGGER = logging.getLogger(__name__)


def includeme(config):
    LOGGER.info("Adding WPS REST API quotation...")
    settings = config.registry.settings
    config.add_route(**sd.service_api_route_info(sd.process_quotes_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_quote_service, settings))
    config.add_route(**sd.service_api_route_info(sd.quotes_service, settings))
    config.add_route(**sd.service_api_route_info(sd.quote_service, settings))
    config.add_route(**sd.service_api_route_info(sd.bills_service, settings))
    config.add_route(**sd.service_api_route_info(sd.bill_service, settings))
    config.add_view(q.get_quote_list, route_name=sd.quotes_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(q.get_quote_list, route_name=sd.process_quotes_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(q.get_quote_info, route_name=sd.quote_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(q.get_quote_info, route_name=sd.process_quote_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(q.request_quote, route_name=sd.process_quotes_service.name,
                    request_method="POST", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(q.execute_quote, route_name=sd.quote_service.name,
                    request_method="POST", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(q.execute_quote, route_name=sd.process_quote_service.name,
                    request_method="POST", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(b.get_bill_list, route_name=sd.bills_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(b.get_bill_info, route_name=sd.bill_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
