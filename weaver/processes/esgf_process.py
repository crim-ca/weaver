import re
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Optional

import cwt  # noqa  # package: esgf-compute-api

from weaver.processes.constants import PACKAGE_FILE_TYPE
from weaver.processes.wps1_process import Wps1Process
from weaver.status import Status
from weaver.utils import fetch_file

if TYPE_CHECKING:
    from weaver.typedefs import JSON
    from typing import Dict, List, Tuple

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


class ESGFProcess(Wps1Process):
    required_inputs = (InputNames.VARIABLE, )

    def execute(self, workflow_inputs, out_dir, expected_outputs):
        # type: (JSON, str, Dict[str, str]) -> None
        """
        Execute an ESGF process from cwl inputs.
        """
        self._check_required_inputs(workflow_inputs)

        api_key = workflow_inputs.get(InputNames.API_KEY)
        inputs = self._prepare_inputs(workflow_inputs)
        domain = self._get_domain(workflow_inputs)

        esgf_process = self._run_process(api_key, inputs, domain)
        self._process_results(esgf_process, out_dir, expected_outputs)

    def _prepare_inputs(self, workflow_inputs):
        # type: (JSON) -> List[cwt.Variable]
        """
        Convert inputs from cwl inputs to ESGF format.
        """
        message = "Preparing execute request for remote ESGF provider."
        self.update_status(message, Percent.PREPARING, Status.RUNNING)

        files = self._get_files_urls(workflow_inputs)
        varname = self._get_variable(workflow_inputs)

        inputs = [cwt.Variable(url, varname) for url in files]

        return inputs

    @staticmethod
    def _get_domain(workflow_inputs):
        # type: (JSON) -> Optional[cwt.Domain]

        dimensions_names = [
            InputNames.TIME,
            InputNames.LAT,
            InputNames.LON,
        ]

        grouped_inputs = defaultdict(dict)

        for dim_name in dimensions_names:
            for param, v in workflow_inputs.items():
                if param.startswith(dim_name + "_"):
                    param_split = param.split("_", 1)[1]
                    grouped_inputs[dim_name][param_split] = v

        # grouped_inputs is of the form:
        # {"lat": {"start": 1, "end": 3, "crs": "values"}}

        # ensure data is casted properly
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
                raise ValueError("ESGF processes only support urls for files inputs.")
            urls.append(location)
        return urls

    @staticmethod
    def _get_variable(workflow_inputs):
        # type: (JSON) -> str
        """
        Get all netcdf files from the cwl inputs.
        """
        if InputNames.VARIABLE not in workflow_inputs:
            raise ValueError("Missing required input " + InputNames.VARIABLE)
        return workflow_inputs[InputNames.VARIABLE]

    def _run_process(self, api_key, inputs, domain=None):
        # type: (str, List[cwt.Variable], Optional[cwt.Domain]) -> cwt.Process
        """
        Run an ESGF process.
        """
        wps = cwt.WPSClient(self.provider, api_key=api_key, verify=True)
        process = wps.processes(self.process)[0]

        message = "Sending request."
        self.update_status(message, Percent.SENDING, Status.RUNNING)

        wps.execute(process, inputs=inputs, domain=domain)

        self._wait(process)

        return process

    def _wait(self, esgf_process, sleep_time=2):
        # type: (cwt.Process, float) -> bool
        """
        Wait for an ESGF process to finish, while reporting its status.
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

                message = "ESGF status: " + status
                self.update_status(message, status_percent, Status.RUNNING)

        update_history()

        while esgf_process.processing:
            update_history()
            time.sleep(sleep_time)

        update_history()

        return esgf_process.succeeded

    def _process_results(self, esgf_process, output_dir, expected_outputs):
        # type: (cwt.Process, str, Dict[str, str]) -> None
        """
        Process the result of the execution.
        """
        if not esgf_process.succeeded:
            message = "Process failed."
            self.update_status(message, Percent.FINISHED, Status.FAILED)
            return

        message = "Process successful."
        self.update_status(message, Percent.COMPUTE_DONE, Status.RUNNING)
        try:
            self._write_outputs(esgf_process.output.uri, output_dir, expected_outputs)
        except Exception:
            message = "Error while downloading files."
            self.update_status(message, Percent.FINISHED, Status.FAILED)
            raise

    def _write_outputs(self, url, output_dir, expected_outputs):
        """
        Write the output netcdf url to a local drive.
        """
        message = "Downloading outputs."
        self.update_status(message, Percent.COMPUTE_DONE, Status.RUNNING)

        nc_outputs = [v for v in expected_outputs.values() if v.lower().endswith(".nc")]
        if len(nc_outputs) > 1:
            raise NotImplementedError("Multiple outputs are not implemented")

        fetch_file(url, output_dir, settings=self.settings)

        message = "Download successful."
        self.update_status(message, Percent.FINISHED, Status.SUCCEEDED)
