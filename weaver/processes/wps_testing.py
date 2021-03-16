from pywps import LiteralInput, LiteralOutput, Process

from weaver.processes.types import PROCESS_TEST


class WpsTestProcess(Process):
    """Test WPS process definition that simply returns its input string as output."""

    type = PROCESS_TEST   # allows to map WPS class

    def __init__(self, **kw):
        # remove duplicates/unsupported keywords
        title = kw.pop("title", kw.get("identifier"))
        version = kw.pop("version", "0.0")
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
        response.update_status("WPS Test Output from process {}...".format(self.identifier), 0)
        response.outputs["test_output"].data = request.inputs["test_input"][0].data
        return response
