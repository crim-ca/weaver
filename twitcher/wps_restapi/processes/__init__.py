import logging
logger = logging.getLogger(__name__)


def includeme(config):
    config.add_route('processes', '/providers/{provider_id}/processes')
    config.add_route('process', '/providers/{provider_id}/processes/{process_id}')
