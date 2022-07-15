from typing import TYPE_CHECKING

from pywps import LiteralInput, LiteralOutput, Process

from weaver.processes.types import ProcessType

if TYPE_CHECKING:
    from typing import Any


# FIXME: transform into official test EchoProcess (https://github.com/crim-ca/weaver/issues/379)
class WpsTestProcess(Process):
    """
    Test WPS process definition that simply returns its input string as output.
    """

    type = ProcessType.TEST   # allows to map WPS class

    def __init__(self, **kw):
        # type: (**Any) -> None

        # remove duplicates/unsupported keywords
        title = kw.pop("title", kw.get("identifier"))
        version = kw.pop("version", "0.0.0")
        kw.pop("inputs", None)
        kw.pop("outputs", None)
        kw.pop("payload", None)
        kw.pop("package", None)

        super(WpsTestProcess, self).__init__(
            self._handler,
            title=title,
            version=version,
            inputs=[LiteralInput("test_input", "Input Request", data_type="string")],
            outputs=[LiteralOutput("test_output", "Output response", data_type="string")],
            store_supported=True,
            status_supported=True,
            **kw
        )

    def _handler(self, request, response):
        response.update_status(f"WPS Test Output from process {self.identifier}...", 0)
        response.outputs["test_output"].data = request.inputs["test_input"][0].data
        return response
