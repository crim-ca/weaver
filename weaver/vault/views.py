import logging
import os
from io import BufferedIOBase
from typing import TYPE_CHECKING

from pyramid.httpexceptions import HTTPBadRequest, HTTPOk
from pyramid.response import FileIter, FileResponse
from pyramid_storage.local import LocalFileStorage

from weaver.datatype import VaultFile
from weaver.database import get_db
from weaver.exceptions import log_unhandled_exceptions
from weaver.formats import get_file_headers
from weaver.store.base import StoreVault
from weaver.vault.utils import get_authorized_file, get_vault_dir, get_vault_path, get_vault_url
from weaver.wps_restapi import swagger_definitions as sd
from weaver.wps_restapi.utils import HTTPHeadFileResponse

if TYPE_CHECKING:
    from typing import Optional, Union

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
    req_file = request.POST.get("file")         # type: Optional[cgi_FieldStorage]
    req_fs = getattr(req_file, "file", None)    # type: Optional[BufferedIOBase]
    if not isinstance(req_fs, BufferedIOBase):
        raise HTTPBadRequest(json={
            "code": "MissingParameterValue",    # FIXME: detail headers multiform ?
            "name": "file",
            "description": sd.BadRequestVaultFileUploadResponse.description,
        })

    # save file to disk from request contents
    # note: 'vault_file.name' includes everything after 'vault_dir' (<id>/<original_name.ext>)
    vault_file = VaultFile("")
    vault_dir = get_vault_dir(request)
    vault_fs = LocalFileStorage(vault_dir)
    vault_file.name = vault_fs.save(req_file, folder=str(vault_file.id))

    db = get_db(request)
    vault = db.get_store(StoreVault)
    vault.save_file(vault_file)

    data = {"description": sd.OkVaultFileUploadedResponse.description}
    data.update(vault_file.json())
    path = get_vault_path(vault_file, request)
    headers = get_file_headers(path)
    headers["Location"] = get_vault_url(vault_file, request)
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
    headers = get_file_headers(path, download_headers=True, content_headers=True, content_type=file.format)
    headers["Location"] = get_vault_url(file, request)
    return HTTPHeadFileResponse(code=200, headers=headers)


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
    # FIXME: add headers ?
    # get_file_headers(path, download_headers=True, content_headers=True, content_type=vault_file.format)
    return resp
