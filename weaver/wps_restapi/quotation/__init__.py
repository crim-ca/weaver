import logging
from typing import TYPE_CHECKING

from weaver.formats import OutputFormat
from weaver.utils import get_settings
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.quotation import bills as b, quotes as q
from weaver.wps_restapi.quotation.utils import check_quotation_supported

if TYPE_CHECKING:
    from pyramid.config import Configurator

LOGGER = logging.getLogger(__name__)


def includeme(config):
    # type: (Configurator) -> None

    settings = get_settings(config)
    if not check_quotation_supported(settings):
        LOGGER.info("Skipping WPS REST API quotation.")
        return

    LOGGER.info("Adding WPS REST API quotation...")
    settings = config.registry.settings
    config.add_route(**sd.service_api_route_info(sd.process_estimator_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_quotes_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_quote_service, settings))
    config.add_route(**sd.service_api_route_info(sd.quotes_service, settings))
    config.add_route(**sd.service_api_route_info(sd.quote_service, settings))
    config.add_route(**sd.service_api_route_info(sd.bills_service, settings))
    config.add_route(**sd.service_api_route_info(sd.bill_service, settings))
    config.add_view(q.get_process_quote_estimator, route_name=sd.process_estimator_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)
    config.add_view(q.update_process_quote_estimator, route_name=sd.process_estimator_service.name,
                    request_method="PUT", renderer=OutputFormat.JSON)
    config.add_view(q.delete_process_quote_estimator, route_name=sd.process_estimator_service.name,
                    request_method="DELETE", renderer=OutputFormat.JSON)
    config.add_view(q.get_quote_list, route_name=sd.quotes_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)
    config.add_view(q.get_quote_list, route_name=sd.process_quotes_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)
    config.add_view(q.get_quote_info, route_name=sd.quote_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)
    config.add_view(q.get_quote_info, route_name=sd.process_quote_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)
    config.add_view(q.request_quote, route_name=sd.process_quotes_service.name,
                    request_method="POST", renderer=OutputFormat.JSON)
    config.add_view(q.execute_quote, route_name=sd.quote_service.name,
                    request_method="POST", renderer=OutputFormat.JSON)
    config.add_view(q.execute_quote, route_name=sd.process_quote_service.name,
                    request_method="POST", renderer=OutputFormat.JSON)
    config.add_view(b.get_bill_list, route_name=sd.bills_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)
    config.add_view(b.get_bill_info, route_name=sd.bill_service.name,
                    request_method="GET", renderer=OutputFormat.JSON)
