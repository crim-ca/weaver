from typing import TYPE_CHECKING

from weaver.processes.constants import PACKAGE_FILE_TYPE, JobInputsOutputsSchema
from weaver.processes.convert import convert_input_values_schema, convert_output_params_schema
from weaver.processes.wps_process_base import OGCAPIRemoteProcessBase, RemoteJobProgress
from weaver.status import Status

if TYPE_CHECKING:
    from typing import Optional

    from weaver.typedefs import (
        CWL_ExpectedOutputs,
        ExecutionInputsMap,
        ExecutionOutputsMap,
        JobInputs,
        JobOutputs,
        JSON,
        UpdateStatusPartialFunction
    )
    from weaver.wps.service import WorkerRequest


class OGCAPIRemoteProcess(OGCAPIRemoteProcessBase):
    process_type = "OGC API"

    def __init__(
        self,
        step_payload,   # type: JSON
        process,        # type: str
        request,        # type: Optional[WorkerRequest]
        update_status,  # type: UpdateStatusPartialFunction
    ):                  # type: (...) -> None
        super(OGCAPIRemoteProcess, self).__init__(step_payload, process, request, update_status)
        self.provider, self.process = process.rsplit("/processes/", 1)
        self.url = self.provider  # dispatch operation re-aggregates the provider with the necessary endpoints
        self.update_status(f"Provider [{self.provider}] is selected for process [{self.process}].",
                           RemoteJobProgress.SETUP, Status.RUNNING)

    def prepare(self, workflow_inputs, expected_outputs):
        # type: (JobInputs, CWL_ExpectedOutputs) -> None

        # by-ref update of "CWL expected outputs" since they are not returned
        # the 'type' is expected by the output staging operation to retrieve a file as remote URI
        # any other 'type' does nothing, but a valid CWL type is needed to avoid raising the validation
        for output in expected_outputs.values():
            cwl_type = PACKAGE_FILE_TYPE if "format" in output else "string"
            output.setdefault("type", cwl_type)

    def format_inputs(self, job_inputs):
        # type: (JobInputs) -> ExecutionInputsMap
        inputs = convert_input_values_schema(job_inputs, JobInputsOutputsSchema.OGC)
        return inputs

    def format_outputs(self, job_outputs):
        # type: (JobOutputs) -> Optional[ExecutionOutputsMap]
        if not job_outputs:
            return None  # avoid 'no output' request from explicit empty container
        outputs = convert_output_params_schema(job_outputs, JobInputsOutputsSchema.OGC)

        # remote the 'type' added by the 'prepare' step
        # this is only to make sure the remote process does not misinterpret the request
        for output in outputs.values():
            output.pop("type", None)

        return outputs
