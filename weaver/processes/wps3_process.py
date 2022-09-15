import logging
import warnings
from typing import TYPE_CHECKING

from pyramid.httpexceptions import HTTPConflict, HTTPForbidden, HTTPNotFound, HTTPOk, HTTPUnauthorized
from pyramid.settings import asbool

from weaver.exceptions import PackageExecutionError
from weaver.formats import ContentType
from weaver.processes import opensearch
from weaver.processes.sources import get_data_source_from_url, retrieve_data_source_url
from weaver.processes.wps_process_base import OGCAPIRemoteProcessBase, RemoteJobProgress, WpsProcessInterface
from weaver.status import Status
from weaver.utils import pass_http_error, request_extra
from weaver.visibility import Visibility
from weaver.warning import MissingParameterWarning
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Tuple, Union

    from weaver.typedefs import (
        AnyHeadersContainer,
        CWL,
        CWL_RuntimeInputsMap,
        HeadersType,
        JSON,
        UpdateStatusPartialFunction
    )
    from weaver.wps.service import WorkerRequest


LOGGER = logging.getLogger(__name__)


class Wps3RemoteJobProgress(RemoteJobProgress):
    SETUP = 1
    PREPARE = 2
    DEPLOY = 3
    VISIBLE = 4
    READY = 5
    EXECUTION = 15
    MONITORING = 20
    STAGE_OUT = 90
    COMPLETED = 100


class Wps3Process(WpsProcessInterface, OGCAPIRemoteProcessBase):
    """
    Remote or local :term:`Process` with :term:`ADES` capabilities, based on :term:`OGC API - Processes` requests.

    If a referenced remote service supports :term:`Process` deployment using an :term:`Application Package`, and
    that inputs point to a resolvable :term:`Data Source`, the execution will be dispatched to that remote location.
    Otherwise, the :term:`Process` is executed locally.

    Most of the core operations are handled by :class:`OGCAPIRemoteProcessBase` since request are sent to another
    :term:`ADES` instance, or `Weaver` itself for :term:`Workflow` steps, both of which are :term:`OGC API - Processes`.
    Additional operations revolve around the resolution of which remote :term:`ADES` to dispatch based on any detected
    :term:`Data Source` location.

    .. seealso::
         - :class:`weaver.processes.wps_process_base.OGCAPIRemoteProcessBase`
    """
    process_type = "WPS-3"  # ADES, EMS or HYBRID (local Application or Workflow)

    def __init__(self,
                 step_payload,      # type: JSON
                 job_order,         # type: CWL_RuntimeInputsMap
                 process,           # type: str
                 request,           # type: WorkerRequest
                 update_status,     # type: UpdateStatusPartialFunction
                 ):                 # type: (...) -> None
        super(Wps3Process, self).__init__(
            request,
            lambda _message, _progress, _status, *args, **kwargs: update_status(
                _message, _progress, _status, self.provider or "local", *args, **kwargs
            )
        )
        self.provider, self.url, self.deploy_body = self.resolve_data_source(step_payload, job_order)
        self.process = process

    def resolve_data_source(self, step_payload, job_order):
        # type: (CWL, CWL_RuntimeInputsMap) -> Tuple[str, str, JSON]
        try:
            # Presume that all EOImage given as input can be resolved to the same ADES
            # So if we got multiple inputs or multiple values for an input, we take the first one as reference
            eodata_inputs = opensearch.get_eo_images_ids_from_payload(step_payload)
            data_url = ""  # data_source will be set to the default ADES if no EOImages (anything but `None`)
            if eodata_inputs:
                step_payload = opensearch.alter_payload_after_query(step_payload)
                value = job_order[eodata_inputs[0]]
                if isinstance(value, list):
                    value = value[0]  # Use the first value to determine the data source
                data_url = value["location"]
                reason = f"(ADES based on {data_url})"
            else:
                reason = "(No EOImage -> Default ADES)"
            data_source = get_data_source_from_url(data_url)
            deploy_body = step_payload
            url = retrieve_data_source_url(data_source)
        except (IndexError, KeyError) as exc:
            LOGGER.error("Error during %s process data source resolution: [%s]", self.process_type, exc, exc_info=exc)
            raise PackageExecutionError(f"Failed resolution of {self.process_type} process data source: [{exc!r}]")

        self.provider = data_source  # fix immediately for below `update_status` call
        self.update_status(f"Provider {data_source} is selected {reason}.",
                           Wps3RemoteJobProgress.SETUP, Status.RUNNING)

        return data_source, url, deploy_body

    def get_user_auth_header(self):
        # type: () -> HeadersType

        # TODO: find a better way to generalize this to Magpie credentials?
        if not asbool(self.settings.get("ades.use_auth_token", True)):
            return {}

        ades_usr = self.settings.get("ades.username", None)
        ades_pwd = self.settings.get("ades.password", None)
        ades_url = self.settings.get("ades.wso2_hostname", None)
        ades_client = self.settings.get("ades.wso2_client_id", None)
        ades_secret = self.settings.get("ades.wso2_client_secret", None)
        access_token = None
        if ades_usr and ades_pwd and ades_url and ades_client and ades_secret:
            ades_body = {
                "grant_type": "password",
                "client_id": ades_client,
                "client_secret": ades_secret,
                "username": ades_usr,
                "password": ades_pwd,
                "scope": "openid",
            }
            ades_headers = {"Content-Type": ContentType.APP_FORM, "Accept": ContentType.APP_JSON}
            ades_access_token_url = f"{ades_url}/oauth2/token"
            cred_resp = request_extra("post", ades_access_token_url,
                                      data=ades_body, headers=ades_headers, settings=self.settings)
            cred_resp.raise_for_status()
            if ContentType.APP_JSON not in cred_resp.headers.get("Content-Type"):
                raise HTTPUnauthorized("Cannot retrieve valid access token using credential or ADES configurations.")
            access_token = cred_resp.json().get("access_token", None)
            if not access_token:
                warnings.warn("Could not retrieve valid access token although response is expected to contain one.",
                              MissingParameterWarning)
        elif self.request and self.request.auth_headers and "Authorization" in self.request.auth_headers:
            # FIXME: consider X-Auth-ADES in case of conflict with Authorization for server that hosts this EMS?
            LOGGER.debug("Detected Authorization header directly specified in request for ADES.")
            access_token = self.request.auth_headers.get("Authorization")
        else:
            warnings.warn(
                "Could not retrieve at least one of required login parameters: "
                "[ades.username, ades.password, ades.wso2_hostname, ades.wso2_client_id, ades.wso2_client_secret]",
                MissingParameterWarning
            )
        return {"Authorization": f"Bearer {access_token}"} if access_token else {}

    def get_auth_headers(self):
        # type: () -> AnyHeadersContainer
        """
        Add specific user access headers for :term:`ADES` if provided in :ref:`Configuration Settings`.
        """
        headers = super(Wps3Process, self).get_auth_headers()
        auth = headers.get("Authorization")
        if not auth:
            headers.update(self.get_user_auth_header())
        return headers

    def is_deployed(self):
        return self.describe_process() is not None

    def is_visible(self):
        # type: (...) -> Union[bool, None]
        """
        Gets the process visibility.

        :returns:
            True/False correspondingly for public/private if visibility is retrievable,
            False if authorized access but process cannot be found,
            None if forbidden access.
        """
        LOGGER.debug("Get process %s visibility request for [%s]", self.process_type, self.process)
        response = self.make_request(method="GET",
                                     url=self.url + sd.process_visibility_service.path.format(process_id=self.process),
                                     retry=False)
        if response.status_code in (HTTPUnauthorized.code, HTTPForbidden.code):
            return None
        if response.status_code == HTTPNotFound.code:
            return False
        if response.status_code == HTTPOk.code:
            json_body = response.json()
            return json_body.get("value") == Visibility.PUBLIC
        response.raise_for_status()

    def set_visibility(self, visibility):
        self.update_status("Updating process visibility on remote ADES.",
                           Wps3RemoteJobProgress.VISIBLE, Status.RUNNING)
        path = self.url + sd.process_visibility_service.path.format(process_id=self.process)
        LOGGER.debug("Update process %s visibility request for [%s] at [%s]", self.process_type, self.process, path)
        response = self.make_request(method="PUT",
                                     url=path,
                                     json={"value": visibility},
                                     retry=False,
                                     swap_error_status_code=HTTPOk.code)
        response.raise_for_status()

    def describe_process(self):
        path = self.url + sd.process_service.path.format(process_id=self.process)
        LOGGER.debug("Describe process %s request for [%s] at [%s]", self.process_type, self.process, path)
        response = self.make_request(method="GET",
                                     url=path,
                                     retry=False,
                                     swap_error_status_code=HTTPOk.code)

        if response.status_code == HTTPOk.code:
            return response.json()
        elif response.status_code == HTTPNotFound.code:
            return None
        response.raise_for_status()

    def deploy(self):
        self.update_status("Deploying process on remote ADES.",
                           Wps3RemoteJobProgress.DEPLOY, Status.RUNNING)
        path = self.url + sd.processes_service.path
        LOGGER.debug("Deploy process %s request for [%s] at [%s]", self.process_type, self.process, path)
        response = self.make_request(method="POST", url=path, json=self.deploy_body, retry=True)
        response.raise_for_status()

    def prepare(self):
        # type: () -> None
        visible = self.is_visible()
        if not visible:  # includes private visibility and non-existing cases
            if visible is None:
                LOGGER.info("Process [%s] access is unauthorized on [%s] - deploying as admin.", self.process, self.url)
            elif visible is False:
                LOGGER.info("Process [%s] is not deployed on [%s] - deploying.", self.process, self.url)
            # TODO: Maybe always redeploy? What about cases of outdated deployed process?
            try:
                self.deploy()
            except Exception as exc:
                pass_http_error(exc, [HTTPConflict])

        if visible:
            LOGGER.info("Process [%s] already deployed and visible on [%s] - executing.", self.process, self.url)
        else:
            LOGGER.info("Process [%s] enforcing to public visibility.", self.process)
            try:
                self.set_visibility(visibility=Visibility.PUBLIC)
            except Exception as exc:
                pass_http_error(exc, HTTPNotFound)
                LOGGER.warning("Process [%s] failed setting public visibility. "
                               "Assuming feature is not supported by ADES and process is already public.", self.process)
