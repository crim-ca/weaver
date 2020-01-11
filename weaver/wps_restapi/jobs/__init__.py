from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.jobs import jobs as j
from weaver.wps_restapi.utils import OUTPUT_FORMAT_JSON
import logging
LOGGER = logging.getLogger(__name__)


def includeme(config):
    LOGGER.info("Adding WPS REST API jobs...")
    settings = config.registry.settings
    config.add_route(**sd.service_api_route_info(sd.jobs_short_service, settings))
    config.add_route(**sd.service_api_route_info(sd.jobs_full_service, settings))
    config.add_route(**sd.service_api_route_info(sd.job_short_service, settings))
    config.add_route(**sd.service_api_route_info(sd.job_full_service, settings))
    config.add_route(**sd.service_api_route_info(sd.results_short_service, settings))
    config.add_route(**sd.service_api_route_info(sd.results_full_service, settings))
    config.add_route(**sd.service_api_route_info(sd.exceptions_short_service, settings))
    config.add_route(**sd.service_api_route_info(sd.exceptions_full_service, settings))
    config.add_route(**sd.service_api_route_info(sd.logs_short_service, settings))
    config.add_route(**sd.service_api_route_info(sd.logs_full_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_jobs_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_job_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_results_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_exceptions_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_logs_service, settings))

    config.add_view(j.get_queried_jobs, route_name=sd.process_jobs_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_queried_jobs, route_name=sd.jobs_short_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_queried_jobs, route_name=sd.jobs_full_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_status, route_name=sd.job_short_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_status, route_name=sd.job_full_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_status, route_name=sd.process_job_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.cancel_job, route_name=sd.job_short_service.name,
                    request_method="DELETE", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.cancel_job, route_name=sd.job_full_service.name,
                    request_method="DELETE", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.cancel_job, route_name=sd.process_job_service.name,
                    request_method="DELETE", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_results, route_name=sd.results_short_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_results, route_name=sd.results_full_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_results, route_name=sd.process_results_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_exceptions, route_name=sd.exceptions_short_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_exceptions, route_name=sd.exceptions_full_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_exceptions, route_name=sd.process_exceptions_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_logs, route_name=sd.logs_short_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_logs, route_name=sd.logs_full_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_logs, route_name=sd.process_logs_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
