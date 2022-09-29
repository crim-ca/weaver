from typing import TYPE_CHECKING

from weaver.processes.wps_process_base import OGCAPIRemoteProcessBase, RemoteJobProgress
from weaver.status import Status

if TYPE_CHECKING:
    from weaver.typedefs import JSON, UpdateStatusPartialFunction
    from weaver.wps.service import WorkerRequest


class OGCAPIRemoteProcess(OGCAPIRemoteProcessBase):
    process_type = "OGC API"

    def __init__(self,
                 step_payload,      # type: JSON
                 process,           # type: str
                 request,           # type: WorkerRequest
                 update_status,     # type: UpdateStatusPartialFunction
                 ):                 # type: (...) -> None
        super(OGCAPIRemoteProcess, self).__init__(step_payload, process, request, update_status)
        self.url = process
        self.provider, self.process = process.rsplit("/processes/", 1)
        self.update_status(f"Provider {self.provider} is selected for process [{self.process}].",
                           RemoteJobProgress.SETUP, Status.RUNNING)
