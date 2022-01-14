import logging
import os
from typing import TYPE_CHECKING

from pyramid.httpexceptions import HTTPBadRequest, HTTPOk
from pyramid.response import FileIter, FileResponse
from pyramid_storage.local import LocalFileStorage

from weaver.datatype import VaultFile
from weaver.database import get_db
from weaver.exceptions import log_unhandled_exceptions
from weaver.store.base import StoreVault
from weaver.utils import get_file_headers
from weaver.vault.utils import get_authorized_file, get_vault_dir, get_vault_path
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from pyramid.httpexceptions import HTTPException
    from pyramid.request import Request

LOGGER = logging.getLogger(__name__)


@sd.vault_service.post(tags=[sd.TAG_VAULT], schema=sd.VaultEndpoint(), response_schemas=sd.post_vault_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def upload_file(request):
    # type: (Request) -> HTTPException
    """
    Upload a file to secured vault.
    """
    req_file = request.POST.get("file")
    req_fs = getattr(req_file, "file", None)  # type:  # FIXME
    if not req_fs:
        raise HTTPBadRequest(json={
            "code": "MissingParameterValue",    # FIXME: detail headers multiform ?
            "name": "file",
            "description": sd.BadRequestVaultFileUploadResponse.description,
        })

    vault_file = VaultFile("")
    vault_dir = get_vault_dir(request)
    vault_fs = LocalFileStorage(vault_dir)
    vault_file.name = vault_fs.save(req_fs, folder=str(vault_file.id))

    db = get_db(request)
    vault = db.get_store(StoreVault)
    vault.save_file(vault_file)

    data = {"description": sd.OkVaultFileUploadedResponse.description}
    data.update(vault_file.json())
    path = get_vault_path(vault_file, request)
    headers = get_file_headers(path)
    return HTTPOk(json=data, headers=headers)


@sd.vault_file_service.decorator("HEAD", tags=[sd.TAG_VAULT], schema=sd.VaultFileEndpoint(),
                                 response_schemas=sd.head_vault_file_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def describe_file(request):
    # type: (Request) -> HTTPException
    """
    Get authorized vault file details without downloading it.
    """
    file = get_authorized_file(request)
    path = get_vault_path(file, request)
    headers = get_file_headers(path)
    return HTTPOk(headers=headers)


@sd.vault_file_service.get(tags=[sd.TAG_VAULT], schema=sd.VaultFileEndpoint(),
                           response_schemas=sd.get_vault_file_responses)
@log_unhandled_exceptions(logger=LOGGER, message=sd.InternalServerErrorResponseSchema.description)
def download_file(request):
    # type: (Request) -> FileResponse
    """
    Download authorized vault file and remove it from the vault.
    """
    file = get_authorized_file(request)

    class FileIterAndDelete(FileIter):
        def close(self):
            super().close()
            os.remove(self.file.name)

    request.environ["wsgi.file_wrapper"] = FileIterAndDelete
    path = get_vault_path(file, request)
    resp = FileResponse(path, request=request)
    return resp
