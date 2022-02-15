import logging
import os

from pywps import LiteralInput, LiteralOutput, Process

from weaver.processes.types import ProcessType

LOGGER = logging.getLogger("PYWPS")


class HelloWPS(Process):
    identifier = "hello"
    title = "Say Hello"
    type = ProcessType.WPS_LOCAL

    def __init__(self, *_, **__):
        inputs = [LiteralInput("name", "Your name", data_type="string")]
        outputs = [LiteralOutput("output", "Output response", data_type="string")]

        super(HelloWPS, self).__init__(
            self._handler,
            identifier=self.identifier,
            title=self.title,
            version="1.4",
            inputs=inputs,
            outputs=outputs,
            store_supported=True,
            status_supported=True
        )

    def _handler(self, request, response):  # noqa
        response.update_status("saying hello...", 0)
        LOGGER.debug("HOME=[%s], Current Dir=[%s]", os.environ.get("HOME"), os.path.abspath(os.curdir))
        response.outputs["output"].data = "Hello " + request.inputs["name"][0].data
        return response
