from typing import TYPE_CHECKING

from pywps import LiteralInput, LiteralOutput, Process

from weaver.processes.types import ProcessType

if TYPE_CHECKING:
    from typing import List, Optional

    from weaver.processes.wps_package import WPS_Input_Type, WPS_Output_Type


# FIXME: transform into official test EchoProcess (https://github.com/crim-ca/weaver/issues/379)
class WpsTestProcess(Process):
    """
    Test WPS process definition that simply returns its input string as output.
    """

    type = ProcessType.TEST   # allows to map WPS class

    def __init__(self, inputs=None, outputs=None, **kw):
        # type: (Optional[List[WPS_Input_Type]], Optional[List[WPS_Output_Type]], **str) -> None
        """
        Initialize the test process with minimal definition requirements.

        If no inputs/outputs are provided, a default literal string is applied for both.
        Otherwise, ``test_input`` and ``test_output`` of the desired type and format should be explicitly provided
        to allow successful execution. Other I/O can be specified, but they will be ignored.
        """

        # remove duplicates/unsupported keywords
        title = kw.pop("title", kw.get("identifier"))
        version = kw.pop("version", "0.0.0")
        kw.pop("payload", None)
        kw.pop("package", None)
        if inputs is None:
            inputs = [LiteralInput("test_input", "Input Request", data_type="string")]
        if outputs is None:
            outputs = [LiteralOutput("test_output", "Output response", data_type="string")]

        super(WpsTestProcess, self).__init__(
            self._handler,
            title=title,
            version=version,
            inputs=inputs,
            outputs=outputs,
            store_supported=True,
            status_supported=True,
            **kw
        )

    def _handler(self, request, response):
        response.update_status(f"WPS Test Output from process {self.identifier}...", 0)
        response.outputs["test_output"].data = request.inputs["test_input"][0].data
        return response
