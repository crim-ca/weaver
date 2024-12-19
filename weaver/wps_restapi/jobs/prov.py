import logging
from typing import TYPE_CHECKING

from weaver.exceptions import log_unhandled_exceptions
from weaver.formats import ContentType
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.jobs.utils import get_job_prov_response

if TYPE_CHECKING:
    from pyramid.config import Configurator

    from weaver.typedefs import AnyResponseType, PyramidRequest

LOGGER = logging.getLogger(__name__)


@sd.provider_prov_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROVIDERS],
    schema=sd.ProviderJobProvEndpoint(),
    accept=sd.JobProvAcceptHeader.validator.choices,
    response_schemas=sd.get_job_prov_responses,
)
@sd.process_prov_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROCESSES],
    schema=sd.ProcessJobProvEndpoint(),
    accept=sd.JobProvAcceptHeader.validator.choices,
    response_schemas=sd.get_job_prov_responses,
)
@sd.job_prov_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE],
    schema=sd.JobProvEndpoint(),
    accept=sd.JobProvAcceptHeader.validator.choices,
    response_schemas=sd.get_job_prov_responses,
)
@sd.provider_prov_info_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROVIDERS],
    schema=sd.ProviderJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.process_prov_info_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROCESSES],
    schema=sd.ProcessJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.job_prov_info_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE],
    schema=sd.JobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.provider_prov_who_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROVIDERS],
    schema=sd.ProviderJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.process_prov_who_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROCESSES],
    schema=sd.ProcessJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.job_prov_who_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE],
    schema=sd.JobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.provider_prov_inputs_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROVIDERS],
    schema=sd.ProviderJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.process_prov_inputs_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROCESSES],
    schema=sd.ProcessJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.job_prov_inputs_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE],
    schema=sd.JobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.provider_prov_inputs_run_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROVIDERS],
    schema=sd.ProviderJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.process_prov_inputs_run_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROCESSES],
    schema=sd.ProcessJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.job_prov_inputs_run_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE],
    schema=sd.JobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.provider_prov_outputs_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROVIDERS],
    schema=sd.ProviderJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.process_prov_outputs_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROCESSES],
    schema=sd.ProcessJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.job_prov_outputs_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE],
    schema=sd.JobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.provider_prov_outputs_run_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROVIDERS],
    schema=sd.ProviderJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.process_prov_outputs_run_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROCESSES],
    schema=sd.ProcessJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.job_prov_outputs_run_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE],
    schema=sd.JobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_responses,  # FIXME
)
@sd.provider_prov_run_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROVIDERS],
    schema=sd.ProviderJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.process_prov_run_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROCESSES],
    schema=sd.ProcessJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.job_prov_run_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE],
    schema=sd.JobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.provider_prov_run_id_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROVIDERS],
    schema=sd.ProviderJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.process_prov_run_id_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROCESSES],
    schema=sd.ProcessJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.job_prov_run_id_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE],
    schema=sd.JobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.provider_prov_runs_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROVIDERS],
    schema=sd.ProviderJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.process_prov_runs_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE, sd.TAG_PROCESSES],
    schema=sd.ProcessJobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@sd.job_prov_runs_service.get(
    tags=[sd.TAG_JOBS, sd.TAG_PROVENANCE],
    schema=sd.JobProvMetadataEndpoint(),
    accept=ContentType.TEXT_PLAIN,
    response_schemas=sd.get_job_prov_metadata_responses,
)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def get_job_prov(request):
    # type: (PyramidRequest) -> AnyResponseType
    """
    Retrieve the provenance details of a job based on the contextual request path.
    """
    return get_job_prov_response(request)


def includeme(config):
    # type: (Configurator) -> None
    LOGGER.info("Adding WPS REST API jobs PROV views...")
    config.add_cornice_service(sd.job_prov_service)
    config.add_cornice_service(sd.job_prov_info_service)
    config.add_cornice_service(sd.job_prov_who_service)
    config.add_cornice_service(sd.job_prov_inputs_service)
    config.add_cornice_service(sd.job_prov_inputs_run_service)
    config.add_cornice_service(sd.job_prov_outputs_service)
    config.add_cornice_service(sd.job_prov_outputs_run_service)
    config.add_cornice_service(sd.job_prov_run_service)
    config.add_cornice_service(sd.job_prov_run_id_service)
    config.add_cornice_service(sd.job_prov_runs_service)
    config.add_cornice_service(sd.process_prov_service)
    config.add_cornice_service(sd.process_prov_info_service)
    config.add_cornice_service(sd.process_prov_who_service)
    config.add_cornice_service(sd.process_prov_inputs_service)
    config.add_cornice_service(sd.process_prov_inputs_run_service)
    config.add_cornice_service(sd.process_prov_outputs_service)
    config.add_cornice_service(sd.process_prov_outputs_run_service)
    config.add_cornice_service(sd.process_prov_run_service)
    config.add_cornice_service(sd.process_prov_run_id_service)
    config.add_cornice_service(sd.process_prov_runs_service)
    config.add_cornice_service(sd.provider_prov_service)
    config.add_cornice_service(sd.provider_prov_info_service)
    config.add_cornice_service(sd.provider_prov_who_service)
    config.add_cornice_service(sd.provider_prov_inputs_service)
    config.add_cornice_service(sd.provider_prov_inputs_run_service)
    config.add_cornice_service(sd.provider_prov_outputs_service)
    config.add_cornice_service(sd.provider_prov_outputs_run_service)
    config.add_cornice_service(sd.provider_prov_run_service)
    config.add_cornice_service(sd.provider_prov_run_id_service)
    config.add_cornice_service(sd.provider_prov_runs_service)
