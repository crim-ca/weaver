import logging
import os
import re
from io import BufferedIOBase
from typing import TYPE_CHECKING

from pyramid.httpexceptions import HTTPOk, HTTPUnprocessableEntity
from pyramid.response import FileIter, FileResponse
from pyramid_storage.exceptions import FileNotAllowed
from pyramid_storage.local import LocalFileStorage

from weaver.database import get_db
from weaver.datatype import VaultFile
from weaver.exceptions import log_unhandled_exceptions
from weaver.formats import get_allowed_extensions
from weaver.owsexceptions import OWSInvalidParameterValue, OWSMissingParameterValue
from weaver.store.base import StoreVault
from weaver.utils import get_file_headers
from weaver.vault.utils import (
    REGEX_VAULT_FILENAME,
    decrypt_from_vault,
    get_authorized_file,
    get_vault_auth,
    get_vault_dir,
    get_vault_path,
    get_vault_url
)
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.utils import HTTPHeadFileResponse

if TYPE_CHECKING:
    from typing import Optional

    from pyramid.httpexceptions import HTTPException
    from pyramid.request import Request
    from webob.compat import cgi_FieldStorage

LOGGER = logging.getLogger(__name__)


@sd.vault_service.post(tags=[sd.TAG_VAULT], schema=sd.VaultUploadEndpoint(), response_schemas=sd.post_vault_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def upload_file(request):
    # type: (Request) -> HTTPException
    """
    Upload a file to secured vault.
    """
    error = "File missing."
    try:
        req_file = request.POST.get("file")         # type: Optional[cgi_FieldStorage]
        req_fs = getattr(req_file, "file", None)    # type: Optional[BufferedIOBase]
    except Exception as exc:
        error = str(exc)
        req_file = req_fs = None
    if not isinstance(req_fs, BufferedIOBase):
        raise OWSMissingParameterValue(json={
            "code": "MissingParameterValue",
            "name": "file",
            "description": sd.BadRequestVaultFileUploadResponse.description,
            "error": error,
        })
    if not re.match(REGEX_VAULT_FILENAME, req_file.filename):
        LOGGER.debug("Invalid filename refused by Vault: [%s]", req_file.filename)
        raise OWSInvalidParameterValue(status=HTTPUnprocessableEntity, json={
            "code": "InvalidParameterValue",
            "name": "filename",
            "description": sd.UnprocessableEntityVaultFileUploadResponse.description,
            "value": str(req_file.filename)
        })

    # save file to disk from request contents
    # note: 'vault_file.name' includes everything after 'vault_dir' (<id>/<original_name.ext>)
    vault_file = VaultFile("")
    vault_dir = get_vault_dir(request)
    vault_fs = LocalFileStorage(vault_dir)
    vault_fs.extensions = get_allowed_extensions()
    try:
        req_file.file = vault_file.encrypt(req_file.file)
        vault_file.name = vault_fs.save(req_file, folder=str(vault_file.id))
    except FileNotAllowed:
        file_ext = os.path.splitext(req_file.filename)
        LOGGER.debug("Invalid file extension refused by Vault: [%s]", file_ext)
        raise OWSInvalidParameterValue(status=HTTPUnprocessableEntity, json={
            "code": "InvalidParameterValue",
            "name": "filename",
            "description": sd.UnprocessableEntityVaultFileUploadResponse.description,
            "value": str(file_ext)
        })

    db = get_db(request)
    vault = db.get_store(StoreVault)
    vault.save_file(vault_file)

    data = {"description": sd.OkVaultFileUploadedResponse.description}
    data.update(vault_file.json())
    path = get_vault_path(vault_file, request)
    headers = get_file_headers(path)
    headers["Content-Location"] = get_vault_url(vault_file, request)
    return HTTPOk(json=data, headers=headers)


@sd.vault_file_service.decorator("HEAD", tags=[sd.TAG_VAULT], schema=sd.VaultFileEndpoint(),
                                 response_schemas=sd.head_vault_file_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def describe_file(request):
    # type: (Request) -> HTTPException
    """
    Get authorized vault file details without downloading it.
    """
    file_id, auth = get_vault_auth(request)
    vault_file = get_authorized_file(file_id, auth, request)
    path = get_vault_path(vault_file, request)
    tmp_file = None
    try:
        tmp_file = decrypt_from_vault(vault_file, path, delete_encrypted=False)
        headers = get_file_headers(tmp_file, download_headers=True,
                                   content_headers=True, content_type=vault_file.format)
        headers["Content-Location"] = get_vault_url(vault_file, request)
    finally:
        if os.path.isfile(tmp_file):
            os.remove(tmp_file)
    return HTTPHeadFileResponse(code=200, headers=headers)


@sd.vault_file_service.get(tags=[sd.TAG_VAULT], schema=sd.VaultFileEndpoint(),
                           response_schemas=sd.get_vault_file_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def download_file(request):
    # type: (Request) -> FileResponse
    """
    Download authorized vault file and remove it from the vault.
    """
    file_id, auth = get_vault_auth(request)
    vault_file = get_authorized_file(file_id, auth, request)

    class FileIterAndDelete(FileIter):
        @property
        def filelike(self):
            return self.file

        def close(self):
            super().close()
            os.remove(self.file.name)

    path = get_vault_path(vault_file, request)
    out_path = decrypt_from_vault(vault_file, path, delete_encrypted=True)
    headers = get_file_headers(out_path, download_headers=True, content_headers=True, content_type=vault_file.format)
    request.environ["wsgi.file_wrapper"] = FileIterAndDelete
    resp = FileResponse(out_path, request=request)
    resp.headers.update(headers)
    return resp
