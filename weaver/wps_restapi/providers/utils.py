import functools
import logging
from typing import TYPE_CHECKING

from pyramid.httpexceptions import HTTPForbidden, HTTPNotFound

from weaver.config import get_weaver_configuration, WEAVER_CONFIGURATIONS_REMOTE
from weaver.database import get_db
from weaver.exceptions import ServiceNotFound
from weaver.store.base import StoreServices
from weaver.utils import get_settings

if TYPE_CHECKING:
    from typing import Any, Callable, List

    from weaver.datatype import Service
    from weaver.typedefs import AnySettingsContainer

LOGGER = logging.getLogger(__name__)


def get_provider_services(container, check=True):
    # type: (AnySettingsContainer, bool) -> List[Service]
    """
    Obtain the list of remote provider services.

    :param container: definition to retrieve settings and database connection.
    :param check: request that all provider services are remotely accessible to fetch metadata from them.
    """
    settings = get_settings(container)
    store = get_db(settings).get_store(StoreServices)
    providers = []
    if not check:
        LOGGER.info("Skipping remote provider service check. Accessibility of listed services will not be validated.")
    for service in store.list_services():
        if check and not service.check_accessible(settings):
            LOGGER.warning("Skipping unresponsive service (%s) [%s]", service.name, service.url)
            continue
        providers.append(service)
    return providers


def forbid_local_only(container):
    # type: (AnySettingsContainer) -> Any
    """
    Raises an HTTP exception forbidding to resume the operation if invalid configuration is detected.
    """
    config = get_weaver_configuration(container)
    if config not in WEAVER_CONFIGURATIONS_REMOTE:
        raise HTTPForbidden(json={
            "description":
                "Invalid provider operation on [{}] instance. "
                "Processes requires unsupported remote execution.".format(config),
        })


def check_provider_requirements(func):
    # type: (Callable[[AnySettingsContainer], Any]) -> Callable[[AnySettingsContainer], Any]
    """
    Decorator to validate if :term:`Provider` operations are applicable for the current `Weaver` instance.
    """
    @functools.wraps(func)
    def forbid_local(container):
        # type: (AnySettingsContainer) -> Any
        forbid_local_only(container)
        return func(container)
    return forbid_local


def get_service(request):
    """
    Get the request service using provider_id from the service store.
    """
    store = get_db(request).get_store(StoreServices)
    provider_id = request.matchdict.get("provider_id")
    try:
        service = store.fetch_by_name(provider_id)
    except ServiceNotFound:
        raise HTTPNotFound("Provider {0} cannot be found.".format(provider_id))
    return service, store
