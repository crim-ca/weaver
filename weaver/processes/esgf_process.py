import re
import time
from collections import defaultdict
from typing import TYPE_CHECKING

import cwt  # noqa  # package: esgf-compute-api

from weaver.processes.constants import PACKAGE_FILE_TYPE
from weaver.processes.wps_process_base import WpsProcessInterface
from weaver.status import Status

if TYPE_CHECKING:
    from typing import List, Optional, Tuple
    from typing_extensions import TypedDict

    from weaver.typedefs import (
        CWL_ExpectedOutputs,
        CWL_RuntimeInputsMap,
        JobResults,
        JSON,
        UpdateStatusPartialFunction
    )
    from weaver.wps.service import WorkerRequest

    ESGFProcessInputs = TypedDict(
        "ESGFProcessInputs",
        {
            "inputs": List[cwt.Variable],
            "domain": Optional[cwt.Domain],
        },
        total=True,
    )

LAST_PERCENT_REGEX = re.compile(r".+ (\d{1,3})$")


class Percent(object):
    PREPARING = 2
    SENDING = 3
    COMPUTE_DONE = 98
    FINISHED = 100


class InputNames(object):
    FILES = "files"
    VARIABLE = "variable"
    API_KEY = "api_key"
    TIME = "time"
    LAT = "lat"
    LON = "lon"


class InputArguments(object):
    START = "start"
    END = "end"
    CRS = "crs"


class ESGFProcess(WpsProcessInterface):
    required_inputs = (InputNames.VARIABLE, )

    def __init__(
        self,
        provider,       # type: str
        process,        # type: str
        request,        # type: WorkerRequest
        update_status,  # type: UpdateStatusPartialFunction
    ):                  # type: (...) -> None
        super().__init__(request=request, update_status=update_status)
        self.provider = provider
        self.process = process
        self.wps_provider = None    # type: Optional[cwt.WPSClient]
        self.wps_process = None     # type: Optional[cwt.Process]

    @staticmethod
    def _get_domain(workflow_inputs):
        # type: (CWL_RuntimeInputsMap) -> Optional[cwt.Domain]

        dimensions_names = [
            InputNames.TIME,
            InputNames.LAT,
            InputNames.LON,
        ]

        grouped_inputs = defaultdict(dict)

        for dim_name in dimensions_names:
            for param, v in workflow_inputs.items():
                if param.startswith(f"{dim_name}_"):
                    param_split = param.split("_", 1)[1]
                    grouped_inputs[dim_name][param_split] = v

        # grouped_inputs is of the form:
        # {"lat": {"start": 1, "end": 3, "crs": "values"}}

        # ensure data is cast properly
        for dim_name, values in grouped_inputs.items():
            for value_name, value in values.items():
                if value_name in [InputArguments.START, InputArguments.END] and value:
                    values[value_name] = float(value)

        allowed_crs = {c.name: c for c in [cwt.VALUES, cwt.INDICES, cwt.TIMESTAMPS]}
        allowed_crs[None] = None

        # fix unintuitive latitude that must be given 'reversed' (start is larger than end)
        if InputNames.LAT in grouped_inputs:
            values = (grouped_inputs[InputNames.LAT][InputArguments.START],
                      grouped_inputs[InputNames.LAT][InputArguments.END])
            grouped_inputs[InputNames.LAT][InputArguments.START] = max(values)
            grouped_inputs[InputNames.LAT][InputArguments.END] = min(values)

        dimensions = []
        for param_name, values in grouped_inputs.items():
            for start_end in [InputArguments.START, InputArguments.END]:
                if start_end not in values:
                    raise ValueError(f"Missing required parameter: {param_name}_{start_end}")
            crs = cwt.VALUES
            if InputArguments.CRS in values:
                if values[InputArguments.CRS] not in allowed_crs:
                    allowed_crs_str = ", ".join(map(str, allowed_crs))
                    raise ValueError(f"CRS must be in [{allowed_crs_str}]")
                crs = allowed_crs[values[InputArguments.CRS]]

            dimension = cwt.Dimension(param_name, values[InputArguments.START], values[InputArguments.END], crs=crs)
            dimensions.append(dimension)

        if dimensions:
            domain = cwt.Domain(
                dimensions
            )
            return domain

    def _check_required_inputs(self, workflow_inputs):
        for required_input in self.required_inputs:
            if required_input not in workflow_inputs:
                raise ValueError(f"Missing required input: {required_input}")

    @staticmethod
    def _get_files_urls(workflow_inputs):
        # type: (JSON) -> List[Tuple[str, str]]
        """
        Get all netcdf files from the cwl inputs.
        """
        urls = []

        files = workflow_inputs[InputNames.FILES]
        if not isinstance(files, list):
            files = [files]

        for cwl_file in files:
            if not cwl_file["class"] == PACKAGE_FILE_TYPE:
                raise ValueError(f"Input named '{InputNames.FILES}' must have a class named 'File'")
            location = cwl_file["location"]
            if not location.startswith("http"):
                raise ValueError("ESGF-CWT processes only support urls for files inputs.")
            urls.append(location)
        return urls

    @staticmethod
    def _get_variable(workflow_inputs):
        # type: (JSON) -> str
        """
        Get all netcdf files from the cwl inputs.
        """
        if InputNames.VARIABLE not in workflow_inputs:
            raise ValueError(f"Missing required input {InputNames.VARIABLE}")
        return workflow_inputs[InputNames.VARIABLE]

    def prepare(self, workflow_inputs, expected_outputs):
        # type: (CWL_RuntimeInputsMap, CWL_ExpectedOutputs) -> None
        """
        Prepare the :term:`ESGF-CWT` :term:`WPS` client.
        """
        headers = {}
        headers.update(self.get_auth_cookies())
        headers.update(self.get_auth_headers())

        api_key = workflow_inputs.get(InputNames.API_KEY)

        self.wps_provider = cwt.WPSClient(
            self.provider,
            api_key=api_key,
            headers=headers,
            verify=True,
        )
        self.wps_process = self.wps_provider.processes(self.process)[0]

    def format_inputs(self, workflow_inputs):
        # type: (CWL_RuntimeInputsMap) -> ESGFProcessInputs
        """
        Convert inputs from cwl inputs to :term:`ESGF-CWT` format.
        """
        message = "Preparing inputs of execute request for remote ESGF-CWT provider."
        self.update_status(message, Percent.PREPARING, Status.RUNNING)

        self._check_required_inputs(workflow_inputs)

        files = self._get_files_urls(workflow_inputs)
        varname = self._get_variable(workflow_inputs)
        domain = self._get_domain(workflow_inputs)
        inputs = [cwt.Variable(url, varname) for url in files]

        return {"inputs": inputs, "domain": domain}

    def dispatch(self, process_inputs, process_outputs):
        # type: (ESGFProcessInputs, CWL_ExpectedOutputs) -> cwt.Process
        """
        Run an :term:`ESGF-CWT` process.
        """
        message = "Sending request."
        self.update_status(message, Percent.SENDING, Status.RUNNING)

        self.wps_provider.execute(self.wps_process, **process_inputs)
        return self.wps_process

    def monitor(self, esgf_process, sleep_time=2):  # pylint: disable=W0237  # renamed parameter to be clearer
        # type: (cwt.Process, float) -> bool
        """
        Wait for an :term:`ESGF-CWT` process to finish, while reporting its status.
        """
        status_history = set()

        def update_history():
            status = esgf_process.status
            status_percent = 0  # python 2 can't mutate nonlocal

            if status not in status_history:
                match = LAST_PERCENT_REGEX.match(status)
                if match:
                    status_percent = int(match.group(1))
                status_percent = max(Percent.SENDING, status_percent)

                status_history.add(status)

                message = f"ESGF-CWT status: {status}"
                self.update_status(message, status_percent, Status.RUNNING)

        update_history()

        while esgf_process.processing:
            update_history()
            time.sleep(sleep_time)

        update_history()

        return esgf_process.succeeded

    def get_results(self, esgf_process):  # pylint: disable=W0237  # renamed parameter to be clearer
        # type: (cwt.Process) -> JobResults
        """
        Process the result of the execution.
        """
        message = "Retrieving outputs."
        self.update_status(message, Percent.COMPUTE_DONE, Status.RUNNING)

        outputs = esgf_process.output
        if not isinstance(outputs, list):
            outputs = [outputs]

        results = [
            {
                "id": out.var_name,
                "href": out.uri,
                "type": out.mime_type,
            }
            for out in outputs
        ]
        return results

    def stage_results(self, results, expected_outputs, out_dir):
        # type: (JobResults, CWL_ExpectedOutputs, str) -> None

        nc_outputs = [v for v in expected_outputs.values() if v["glob"].lower().endswith(".nc")]
        if len(nc_outputs) > 1:
            raise NotImplementedError("Multiple outputs are not implemented")

        super().stage_results(results, expected_outputs, out_dir)
        message = "Download successful."
        self.update_status(message, Percent.FINISHED, Status.RUNNING)
