import re

import logging
import os
from tempfile import mkdtemp
from typing import TYPE_CHECKING

import colander
from pyramid.httpexceptions import HTTPBadRequest, HTTPForbidden, HTTPGone

from weaver.database import get_db
from weaver.datatype import VaultFile
from weaver.store.base import StoreVault
from weaver.utils import get_header, get_settings, get_weaver_url, repr_json
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Dict, Optional

    from pyramid.request import Request

    from weaver.typedefs import AnySettingsContainer

LOGGER = logging.getLogger(__name__)

REGEX_VAULT_TOKEN = re.compile(r"^[a-f0-9]{{{}}}$".format(VaultFile.bytes * 2))
REGEX_VAULT_UUID = re.compile(r"^[a-f0-9]{8}(?:-?[a-f0-9]{4}){3}-?[a-f0-9]{12}$")


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


def parse_vault_token(header, unique=False):
    # type: (Optional[str], bool) -> Dict[Optional[str], str]
    """
    Parse the authorization header value to retrieve all :term:`Vault` access tokens and optional file UUID.

    .. seealso::
        - Definition of expected format in :ref:`file_vault_token`.
        - :class:`sd.VaultFileAuthorizationHeader`

    :param header: Authorization header to parse.
    :param unique: Whether only one or multiple tokens must be retrieved.
    :return: Found mapping of UUID to access token. If unique, UUID can be ``None``.
    """
    if not isinstance(header, str):
        return {}
    header = header.lower()
    if unique and "," in header:
        return {}
    auth_tokens = header.split(",")
    if not auth_tokens:
        return {}
    if len(auth_tokens) > 1 and unique:  # cannot pick which one applies
        return {}
    vault_tokens = {}
    for auth in auth_tokens:
        auth = auth.strip()
        if not unique and ";" not in auth:
            return {}
        if unique and ";" not in auth:
            token = auth
            param = "="
        else:
            token, param = auth.split(";", 1)
        if param.strip() == "":  # final ';' to ignore
            param = "="
        token = token.split("token ")[-1].strip()
        param = param.split("=")
        if not len(param) == 2:
            return {}
        value = param[1].strip()
        param = param[0].strip()
        if param != "id" and not (value or unique):
            return {}
        if param and unique and not value:  # explicitly provided parameter although optional is allowed
            return {}
        if value and value.startswith("\"") and value.endswith("\""):
            value = value[1:-1]
        value_match = REGEX_VAULT_UUID.match(value) if value else None
        token_match = REGEX_VAULT_TOKEN.match(token) if token else None
        if not token_match:
            return {}
        token_match = token_match[0]
        if not value_match and not (unique and not value):  # allow omitted 'id' if unique, unless explicitly given
            return {}
        value_match = None if (unique and not param) else value_match[0]
        if vault_tokens.get(value_match) is not None:
            return {}  # cannot pick duplicates, drop both
        vault_tokens[value_match] = token_match
    return vault_tokens


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
            "description": sd.BadRequestVaultFileAccessResponse.description,
            "error": colander.Invalid.__name__,
            "cause": str(ex),
            "value": repr_json(ex.value or dict(request.matchdict), force_string=False),
        })
    auth = get_header(sd.VaultFileAuthorizationHeader.name, request.headers)
    vault_token = parse_vault_token(auth, unique=True)
    token = vault_token.get(None, vault_token.get(file_id))
    if not token:
        # note:
        #   401 not applicable since no no Authentication endpoint for the Vault
        #   RFC 2616 requires that a 401 response be accompanied by an RFC 2617 WWW-Authenticate
        msg = "Missing authorization token to obtain access to vault file."
        if auth:  # if header provided but parsed as invalid
            msg = "Incorrectly formed authorization token to obtain access to vault file."
        if vault_token and list(vault_token)[0] not in [None, file_id]:
            msg = "Mismatching Vault UUID specified in authorization header."
        raise HTTPForbidden(json={
            "code": "InvalidHeaderValue",
            "name": sd.VaultFileAuthorizationHeader.name,
            "description": msg,
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
