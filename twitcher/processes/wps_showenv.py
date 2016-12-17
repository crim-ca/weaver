import os
from pprint import pformat

from pywps import Process, LiteralOutput

import logging
logger = logging.getLogger("PYWPS")


class ShowEnv(Process):
    def __init__(self):
        inputs = []
        outputs = [
            LiteralOutput('output', 'Output response',
                          data_type='string')]

        super(ShowEnv, self).__init__(
            self._handler,
            identifier='showenv',
            title='Show Process Environment',
            version='1.0',
            inputs=inputs,
            outputs=outputs,
            store_supported=True,
            status_supported=True
        )

    def _handler(self, request, response):
        logger.info("run showenv ...")
        response.outputs['output'].data = "Environment: {}".format(pformat(os.environ, indent=4))
        return response
