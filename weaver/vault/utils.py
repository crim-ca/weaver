import logging
import os
import re
import tempfile
import uuid
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import colander
from pyramid.httpexceptions import HTTPBadRequest, HTTPForbidden, HTTPGone

from weaver.database import get_db
from weaver.datatype import VaultFile
from weaver.formats import repr_json
from weaver.store.base import StoreVault
from weaver.utils import get_header, get_secure_path, get_settings, get_weaver_url, is_uuid
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Dict, Optional, Tuple, Union

    from pyramid.request import Request

    from weaver.typedefs import AnySettingsContainer, AnyUUID, TypedDict

    # PyWPS-like Complex InputData with additional authentication for Vault access
    VaultInputData = TypedDict("VaultInputData", {"identifier": str, "href": str, "auth": Dict[str, str]}, total=False)

LOGGER = logging.getLogger(__name__)

REGEX_VAULT_TOKEN = re.compile(fr"^[a-f0-9]{{{VaultFile.bytes * 2}}}$")
REGEX_VAULT_UUID = re.compile(r"^[a-f0-9]{8}(?:-?[a-f0-9]{4}){3}-?[a-f0-9]{12}$")
REGEX_VAULT_FILENAME = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9._-]*[a-zA-Z0-9_-])?\.[a-zA-Z0-9_-]+$")


def get_vault_dir(container=None):
    # type: (Optional[AnySettingsContainer]) -> str
    """
    Get the base directory of the secure file vault.
    """
    settings = get_settings(container)
    vault_dir = settings.get("weaver.vault_dir")
    if not vault_dir:
        vault_dir = tempfile.mkdtemp(prefix="weaver_vault_")
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
    vault_path = os.path.join(vault_dir, file.name)
    vault_path = get_secure_path(vault_path)
    return vault_path


def get_vault_url(file, container=None):
    # type: (Union[VaultFile, uuid.UUID, str], Optional[AnySettingsContainer]) -> str
    """
    Obtain the vault link corresponding to the file.
    """
    if isinstance(file, uuid.UUID) or is_uuid(file):
        file_id = str(file)
    else:
        file_id = file.id
    settings = get_settings(container)
    base_url = get_weaver_url(settings)
    vault_url = base_url + sd.vault_file_service.path.format(file_id=file_id)
    return vault_url


def map_vault_location(reference, container=None, url=False, exists=True):
    # type: (str, AnySettingsContainer, bool, bool) -> Optional[str]
    """
    Convert back and forth between the URL and local path references of the :term:`Vault` file.

    .. seealso::
        Similar operation to :func:`weaver.wps.utils.map_wps_output_location`.

    .. warning::
        Does not validate access token to retrieve the file. It is assumed that pre-valuation was accomplished.

    :param reference: Local file path or file URL to be mapped.
    :param container: Retrieve application settings.
    :param url: Perform URL mapping (local path -> URL endpoint), or map to local path (URL -> local path).
    :param exists: Ensure that the mapped file exists, otherwise don't map it (otherwise ``None``).
    :returns: Mapped reference if applicable, otherwise ``None``.
    """
    scheme = urlparse(reference).scheme
    base = get_vault_dir(container)
    if url and scheme == "file":
        reference = reference[7:]
    if scheme in ["http", "https"]:
        file_path = sd.vault_file_service.path.format(file_id="")
        file_id = reference.split(file_path, 1)[-1]
    elif reference.startswith(base):
        file_base = f"{base}/" if not base.endswith("/") else base
        file_id = reference.split(file_base)[-1].split("/", 1)[0]
    else:
        file_id = ""
    if not file_id:
        return None

    db = get_db(container)
    vault = db.get_store(StoreVault)
    file = vault.get_file(file_id, nothrow=True)
    href = get_vault_url(file, container)
    path = get_vault_path(file, container)

    if exists and not os.path.isfile(path):
        return None
    return href if url else path


def parse_vault_token(header, unique=False):
    # type: (Optional[str], bool) -> Dict[Optional[str], str]
    """
    Parse the authorization header value to retrieve all :term:`Vault` access tokens and optional file UUID.

    .. seealso::
        - Definition of expected format in :ref:`file_vault_token`.
        - :class:`sd.XAuthVaultFileHeader`

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


def get_vault_auth(request):
    # type: (Request) -> Tuple[AnyUUID, Optional[str]]
    """
    Obtain the requested file reference and parsed access token from the :term:`Vault` authorization header.

    :param request: Request containing reference file UUID and authorization headers.
    :return: Extracted file reference and authentication token.
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
    auth = get_header(sd.XAuthVaultFileHeader.name, request.headers)
    return file_id, auth


def get_authorized_file(file_id, auth_token, container=None):
    # type: (AnyUUID, str, Optional[AnySettingsContainer]) -> VaultFile
    """
    Obtain the requested file if access is granted.

    :param file_id: Vault storage reference file UUID.
    :param auth_token: Token to obtain access to the file.
    :param container: Application settings.
    :return: Authorized file.
    :raises: Appropriate HTTP exception according to use case.
    """
    vault_token = parse_vault_token(auth_token, unique=True)
    token = vault_token.get(None, vault_token.get(file_id))
    if not token:
        # note:
        #   401 not applicable since no no Authentication endpoint for the Vault
        #   RFC 2616 requires that a 401 response be accompanied by an RFC 2617 WWW-Authenticate
        msg = "Missing authorization token to obtain access to vault file."
        if auth_token:  # if header provided but parsed as invalid
            msg = "Incorrectly formed authorization token to obtain access to vault file."
        if vault_token and list(vault_token)[0] not in [None, file_id]:
            msg = "Mismatching Vault UUID specified in authorization header."
        raise HTTPForbidden(json={
            "code": "InvalidHeaderValue",
            "name": sd.XAuthVaultFileHeader.name,
            "description": msg,
            "value": repr_json(auth_token, force_string=False),
        })

    db = get_db(container)
    vault = db.get_store(StoreVault)
    file = vault.get_file(file_id, nothrow=True)  # don't indicate if not found when unauthorized
    if not VaultFile.authorized(file, token):
        raise HTTPForbidden(json={
            "code": "InvalidHeaderValue",
            "name": sd.XAuthVaultFileHeader.name,
            "description": sd.ForbiddenVaultFileDownloadResponse.description,
        })

    file_path = get_vault_path(file, container)
    if not os.path.isfile(file_path):
        raise HTTPGone(json={
            "code": "VaultFileGone",
            "value": str(file.id),
            "description": sd.GoneVaultFileDownloadResponse.description,
        })
    return file


def decrypt_from_vault(vault_file, path, out_dir=None, delete_encrypted=False):
    # type: (VaultFile, str, Optional[str], bool) -> str
    """
    Decrypts a :term:`Vault` file and optionally removes its encrypted version.

    :param vault_file: Reference file in :term:`Vault`.
    :param path: Expected location of the encrypted file.
    :param out_dir: Desired output location, or temporary directory.
    :param delete_encrypted: Delete original encrypted file after decryption for output.
    :return: Output location of the decrypted file.
    """
    ext = os.path.splitext(path)[-1]
    with tempfile.NamedTemporaryFile(suffix=ext, mode="w+b", delete=False, dir=out_dir) as out_file:
        with open(path, mode="r+b") as vault_fd:
            data = vault_file.decrypt(vault_fd)
        out_file.write(data.getbuffer())  # noqa
        out_file.flush()
        out_file.seek(0)
        if delete_encrypted:
            os.remove(path)
    vault_path = get_secure_path(out_file.name)
    return vault_path
