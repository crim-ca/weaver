from weaver.processes.wps_process_base import WpsProcessInterface
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from weaver.typedefs import UpdateStatusPartialFunction
    from typing import AnyStr


class WpsBuiltinProcess(WpsProcessInterface):
    def __init__(self,
                 process,           # type: AnyStr
                 update_status,     # type: UpdateStatusPartialFunction
                 ):
        self.process = process
        self.update_status = update_status

    def execute(self, workflow_inputs, out_dir, expected_outputs):
        pass
