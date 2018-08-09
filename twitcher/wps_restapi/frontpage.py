from twitcher.wps_restapi import swagger_definitions as sd
from pyramid.view import view_config

import logging
logger = logging.getLogger(__name__)


@sd.api_frontpage_service.get(tags=[sd.api_tag], renderer='json',
                              schema=sd.FrontpageEndpoint(), response_schemas=sd.get_api_frontpage_responses)
def frontpage(request):
    """Frontpage of Twitcher."""
    settings = request.registry.settings
    return {'message': 'hello', 'configuration': settings.get('twitcher.configuration', 'default')}
