import logging
import os
from tempfile import mkdtemp
from typing import TYPE_CHECKING

import colander
from pyramid.httpexceptions import HTTPBadRequest, HTTPForbidden, HTTPGone, HTTPUnauthorized

from weaver.database import get_db
from weaver.datatype import VaultFile
from weaver.store.base import StoreVault
from weaver.utils import get_header, get_settings, get_weaver_url, repr_json
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Optional

    from pyramid.request import Request

    from weaver.typedefs import AnySettingsContainer

LOGGER = logging.getLogger(__name__)


def get_vault_dir(container=None):
    # type: (Optional[AnySettingsContainer]) -> str
    """
    Get the base directory of the secure file vault.
    """
    settings = get_settings(container)
    vault_dir = settings.get("weaver.vault_dir")
    if not vault_dir:
        vault_dir = mkdtemp(prefix="weaver_vault_")
        LOGGER.warning("Setting 'weaver.vault_dir' undefined. Using random vault base directory: [%s]", vault_dir)
        settings["weaver.vault_dir"] = vault_dir
    os.makedirs(vault_dir, mode=0o755, exist_ok=True)
    return vault_dir


def get_vault_path(file, container=None):
    # type: (VaultFile, Optional[AnySettingsContainer]) -> str
    """
    Get the full path of the vault file.
    """
    vault_dir = get_vault_dir(container)
    return os.path.join(vault_dir, file.name)


def get_vault_url(file, container=None):
    # type: (VaultFile, Optional[AnySettingsContainer]) -> str
    """
    Obtain the vault link corresponding to the file.
    """
    settings = get_settings(container)
    base_url = get_weaver_url(settings)
    vault_url = base_url + sd.vault_file_service.path.format(file_id=file.id)
    return vault_url


def get_authorized_file(request):
    # type: (Request) -> VaultFile
    """
    Obtain the requested file if access is granted.

    :param request: Request containing reference file UUID and authorization headers.
    :return: Authorized file.
    :raises: Appropriate HTTP exception according to use case.
    """
    try:
        file_id = request.matchdict.get("file_id")
        file_id = sd.VaultFileID().deserialize(file_id)
    except colander.Invalid as ex:
        raise HTTPBadRequest(json={
            "code": "VaultInvalidParameter",
            "description": sd.BadRequestVaultFileDownloadResponse.description,
            "error": colander.Invalid.__name__,
            "cause": str(ex),
            "value": repr_json(ex.value or dict(request.matchdict), force_string=False),
        })
    auth = get_header(sd.VaultFileAuthorizationHeader.name, request.headers)
    token = auth.split("token ")[-1] if isinstance(auth, str) else None
    if not token:
        raise HTTPUnauthorized(json={
            "code": "InvalidHeaderValue",
            "name": sd.VaultFileAuthorizationHeader.name,
            "description": sd.UnauthorizedVaultFileDownloadResponse.description,
            "value": repr_json(auth, force_string=False),
        })

    db = get_db(request)
    vault = db.get_store(StoreVault)
    file = vault.get_file(file_id, nothrow=True)  # don't indicate if not found if unauthorized
    if not VaultFile.authorized(file, token):
        raise HTTPForbidden(json={
            "code": "InvalidHeaderValue",
            "name": sd.VaultFileAuthorizationHeader.name,
            "description": sd.ForbiddenVaultFileDownloadResponse.description,
        })

    file_path = get_vault_path(file, request)
    if not os.path.isfile(file_path):
        raise HTTPGone(json={
            "code": "VaultFileGone",
            "value": str(file.id),
            "description": sd.GoneVaultFileDownloadResponse.description,
        })

    return file
