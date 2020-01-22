from weaver.processes.types import PROCESS_WPS

from pywps import LiteralInput, LiteralOutput, Process

import logging
import os

LOGGER = logging.getLogger("PYWPS")


class HelloWPS(Process):
    identifier = 'hello'
    title = 'Say Hello'
    type = PROCESS_WPS

    def __init__(self):
        inputs = [
            LiteralInput('name', 'Your name', data_type='string')]
        outputs = [
            LiteralOutput('output', 'Output response',
                          data_type='string')]

        super(HelloWPS, self).__init__(
            self._handler,
            identifier=self.identifier,
            title=self.title,
            version='1.4',
            inputs=inputs,
            outputs=outputs,
            store_supported=True,
            status_supported=True
        )

    # noinspection PyMethodMayBeStatic
    def _handler(self, request, response):
        response.update_status("saying hello...", 0)
        LOGGER.debug("HOME=[%s], Current Dir=[%s]", os.environ.get("HOME"), os.path.abspath(os.curdir))
        response.outputs["output"].data = "Hello " + request.inputs["name"][0].data
        return response
