from pywps import Process, LiteralInput, LiteralOutput
from twitcher.processes.types import PROCESS_TEST


class WpsTestProcess(Process):
    type = PROCESS_TEST   # allows to map WPS class

    def __init__(self, **kw):
        # remove duplicates/unsupported keywords
        kw.pop('title', None)
        kw.pop('inputs', None)
        kw.pop('outputs', None)
        kw.pop('version', None)
        kw.pop('payload', None)
        kw.pop('package', None)

        super(WpsTestProcess, self).__init__(
            self._handler,
            title='WpsTestProcess',
            version='0.0',
            inputs=[LiteralInput('test_input', 'Input Request', data_type='string')],
            outputs=[LiteralOutput('test_output', 'Output response', data_type='string')],
            store_supported=True,
            status_supported=True,
            **kw
        )

    # noinspection PyMethodMayBeStatic
    def _handler(self, request, response):
        response.update_status("WPS Test Output from process {}...".format(self.identifier), 0)
        response.outputs['test_output'].data = request.inputs['test_input'][0].data
        return response
