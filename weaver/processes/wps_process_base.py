from abc import abstractmethod
from time import sleep
from typing import TYPE_CHECKING

from pyramid.httpexceptions import HTTPBadGateway
from pyramid_celery import celery_app as app

from weaver.formats import CONTENT_TYPE_APP_JSON
from weaver.utils import get_cookie_headers, get_settings, request_extra
from weaver.wps.utils import get_wps_output_dir, get_wps_output_url

if TYPE_CHECKING:
    from weaver.typedefs import CWL_RuntimeInputsMap
    from typing import Dict
    from pywps.app import WPSRequest


class WpsProcessInterface(object):
    """
    Common interface for WpsProcess to be used in ``CWL`` jobs.
    """

    @abstractmethod
    def execute(self,
                workflow_inputs,        # type: CWL_RuntimeInputsMap
                out_dir,                # type: str
                expected_outputs,       # type: Dict[str, str]
                ):
        """
        Execute a remote process using the given inputs.
        The function is expected to monitor the process and update the status.
        Retrieve the expected outputs and store them in the ``out_dir``.

        :param workflow_inputs: `CWL` job dict
        :param out_dir: directory where the outputs must be written
        :param expected_outputs: expected value outputs as `{'id': 'value'}`
        """
        raise NotImplementedError

    def __init__(self, request):
        # type: (WPSRequest) -> None
        self.request = request
        if self.request.http_request:
            self.cookies = get_cookie_headers(self.request.http_request.headers)
        else:
            self.cookies = {}
        self.headers = {"Accept": CONTENT_TYPE_APP_JSON, "Content-Type": CONTENT_TYPE_APP_JSON}
        self.settings = get_settings(app)

    def make_request(self, method, url, retry, status_code_mock=None, **kwargs):
        response = request_extra(method, url=url, settings=self.settings,
                                 headers=self.headers, cookies=self.cookies, **kwargs)
        # TODO: Remove patch for Geomatys unreliable server
        if response.status_code == HTTPBadGateway.code and retry:
            sleep(10)
            response = self.make_request(method, url, False, **kwargs)
        if response.status_code == HTTPBadGateway.code and status_code_mock:
            response.status_code = status_code_mock
        return response

    @staticmethod
    def host_file(file_name):
        settings = get_settings(app)
        weaver_output_url = get_wps_output_url(settings)
        weaver_output_dir = get_wps_output_dir(settings)
        file_name = file_name.replace("file://", "")

        if not file_name.startswith(weaver_output_dir):
            raise Exception("Cannot host files outside of the output path : {0}".format(file_name))
        return file_name.replace(weaver_output_dir, weaver_output_url)
