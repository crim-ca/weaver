import logging

from weaver.formats import OUTPUT_FORMAT_JSON
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.jobs import jobs as j

LOGGER = logging.getLogger(__name__)


def includeme(config):
    LOGGER.info("Adding WPS REST API jobs...")
    settings = config.registry.settings
    config.add_route(**sd.service_api_route_info(sd.jobs_service, settings))
    config.add_route(**sd.service_api_route_info(sd.job_service, settings))
    config.add_route(**sd.service_api_route_info(sd.job_results_service, settings))
    config.add_route(**sd.service_api_route_info(sd.job_outputs_service, settings))
    config.add_route(**sd.service_api_route_info(sd.job_inputs_service, settings))
    config.add_route(**sd.service_api_route_info(sd.job_exceptions_service, settings))
    config.add_route(**sd.service_api_route_info(sd.job_logs_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_job_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_jobs_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_results_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_outputs_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_inputs_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_exceptions_service, settings))
    config.add_route(**sd.service_api_route_info(sd.provider_logs_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_jobs_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_job_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_results_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_outputs_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_inputs_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_exceptions_service, settings))
    config.add_route(**sd.service_api_route_info(sd.process_logs_service, settings))

    config.add_view(j.get_queried_jobs, route_name=sd.process_jobs_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_queried_jobs, route_name=sd.jobs_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_queried_jobs, route_name=sd.provider_jobs_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_status, route_name=sd.job_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_status, route_name=sd.provider_job_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_status, route_name=sd.process_job_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.cancel_job, route_name=sd.job_service.name,
                    request_method="DELETE", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.cancel_job, route_name=sd.provider_job_service.name,
                    request_method="DELETE", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.cancel_job, route_name=sd.process_job_service.name,
                    request_method="DELETE", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_results, route_name=sd.job_results_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_results, route_name=sd.provider_results_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_results, route_name=sd.process_results_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_outputs, route_name=sd.job_outputs_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_outputs, route_name=sd.provider_outputs_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_outputs, route_name=sd.process_outputs_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_inputs, route_name=sd.job_inputs_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_inputs, route_name=sd.provider_inputs_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_inputs, route_name=sd.process_inputs_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_exceptions, route_name=sd.job_exceptions_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_exceptions, route_name=sd.provider_exceptions_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_exceptions, route_name=sd.process_exceptions_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_logs, route_name=sd.job_logs_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_logs, route_name=sd.provider_logs_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
    config.add_view(j.get_job_logs, route_name=sd.process_logs_service.name,
                    request_method="GET", renderer=OUTPUT_FORMAT_JSON)
