import logging
logger = logging.getLogger(__name__)


def includeme(config):
    config.add_route('processes', '/providers/{provider_name}/processes')
    config.add_route('process', '/providers/{provider_name}/processes/{process_id}')
