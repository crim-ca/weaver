import logging
logger = logging.getLogger(__name__)


def includeme(config):
    config.add_route('jobs', '/jobs')
    config.add_route('job', '/providers/{provider_name}/processes/{process_id}/jobs/{job_id}')
    config.add_route('job', '/jobs/{job_id}')
    config.add_route('outputs', '/providers/{provider_name}/processes/{process_id}/jobs/{job_id}/outputs')
    config.add_route('outputs', '/jobs/{job_id}/outputs')
    config.add_route('output', '/providers/{provider_name}/processes/{process_id}/jobs/{job_id}/outputs/{output_id}')
    config.add_route('output', '/jobs/{job_id}/outputs/{output_id}')
