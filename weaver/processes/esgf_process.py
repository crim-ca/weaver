import re
import time
from collections import defaultdict
from os.path import join

from typing import AnyStr, TYPE_CHECKING, Optional
import logging
import requests
import cwt

from weaver.status import STATUS_RUNNING, STATUS_SUCCEEDED, STATUS_FAILED
from weaver.processes.wps1_process import Wps1Process

if TYPE_CHECKING:
    from weaver.typedefs import JsonBody
    from typing import AnyStr, Dict, List, Tuple

LOGGER = logging.getLogger(__name__)


class Percent:
    PREPARING = 2
    SENDING = 3
    COMPUTE_DONE = 98
    FINISHED = 100


class InputNames:
    files = "files"
    variable = "variable"
    api_key = "api_key"
    time = "time"
    lat = "lat"
    lon = "lon"


class ESGFProcess(Wps1Process):
    required_inputs = ("api_key", "variable")

    def execute(self, workflow_inputs, output_dir, expected_outputs):
        # type: (JsonBody, AnyStr, Dict[AnyStr, AnyStr]) -> None
        """Execute an ESGF process from cwl inputs"""
        LOGGER.debug("Executing ESGF process {}".format(self.process))

        self._check_required_inputs(workflow_inputs)

        api_key = workflow_inputs[InputNames.api_key]
        inputs = self._prepare_inputs(workflow_inputs)
        domain = self._get_domain(workflow_inputs)

        esgf_process = self._run_process(api_key, inputs, domain)
        self._process_results(esgf_process, output_dir, expected_outputs)

    def _prepare_inputs(self, workflow_inputs):
        # type: (JsonBody) -> List[cwt.Variable]
        """Convert inputs from cwl inputs to ESGF format"""
        message = "Preparing execute request for remote ESGF provider."
        self.update_status(message, Percent.PREPARING, STATUS_RUNNING)

        LOGGER.debug("Parsing inputs")

        files = self._get_files_urls(workflow_inputs)
        varname = self._get_variable(workflow_inputs)

        LOGGER.debug("Creating esgf-compute-api inputs")

        inputs = [cwt.Variable(url, varname) for url in files]

        return inputs

    def _get_domain(self, workflow_inputs):
        # type: (JsonBody) -> Optional[cwt.Domain]

        dimensions_names = [
            InputNames.time,
            InputNames.lat,
            InputNames.lon,
        ]

        grouped_inputs = defaultdict(dict)

        for dim_name in dimensions_names:
            for param, v in workflow_inputs.items():
                if param.startswith(dim_name + "_"):
                    param_splitted = param.split("_", 1)[1]
                    grouped_inputs[dim_name][param_splitted] = v

        # grouped_inputs is of the form:
        # {"lat": {"start": 1, "end": 3, "crs": "values"}}

        allowed_crs = {c.name: c for c in [cwt.VALUES, cwt.INDICES, cwt.TIMESTAMPS]}

        dimensions = []
        for param_name, values in grouped_inputs.items():
            for start_end in ["start", "end"]:
                if start_end not in values:
                    raise ValueError("Missing required parameter: {}_{}".format(param_name, start_end))
            crs = cwt.VALUES
            if "crs" in values:
                if values["crs"] not in allowed_crs:
                    raise ValueError("CRS must be in {}".format(", ".join(allowed_crs)))
                crs = allowed_crs[values["crs"]]

            dimension = cwt.Dimension(param_name, values["start"], values["end"], crs=crs)
            dimensions.append(dimension)

        if dimensions:
            domain = cwt.Domain(
                dimensions
            )
            return domain

    def _check_required_inputs(self, workflow_inputs):
        for required_input in self.required_inputs:
            if required_input not in workflow_inputs:
                raise ValueError("Missing required input: {}".format(required_input))

    def _get_files_urls(self, workflow_inputs):
        # type: (JsonBody) -> List[Tuple[str, str]]
        """Get all netcdf files from the cwl inputs"""
        urls = []

        files = workflow_inputs[InputNames.files]
        if not isinstance(files, list):
            files = [files]

        for cwl_file in files:
            if not cwl_file["class"] == "File":
                raise ValueError("'{}' inputs must have a class named 'File'".format(InputNames.files))
            location = cwl_file["location"]
            if not location.startswith("http"):
                raise ValueError("ESGF processes only support urls for files inputs.")
            urls.append(location)
        return urls

    def _get_variable(self, workflow_inputs):
        # type: (JsonBody) -> str
        """Get all netcdf files from the cwl inputs"""
        if InputNames.variable not in workflow_inputs:
            raise ValueError("Missing required input: variable")
        return workflow_inputs[InputNames.variable]

    def _run_process(self, api_key, inputs, domain=None):
        # type: (str, List[cwt.Variable], Optional[cwt.Domain]) -> cwt.Process
        """Run an ESGF process"""
        LOGGER.debug("Connecting to ESGF WPS")

        wps = cwt.WPSClient(self.provider, api_key=api_key, verify=False)
        process = wps.processes(self.process)[0]

        message = "Sending request."
        LOGGER.debug(message)
        self.update_status(message, Percent.SENDING, STATUS_RUNNING)

        wps.execute(process, inputs=inputs, domain=domain)

        LOGGER.debug("Waiting for result")

        self._wait(process)

        return process

    def _wait(self, esgf_process, sleep_time=2):
        # type: (cwt.Process, float) -> bool
        """Wait for an ESGF process to finish, while reporting its status"""
        status_history = set()

        status_percent = [0]  # python 2 can't mutate nonlocal
        last_percent_regex = re.compile(r".+ (\d{1,3})$")

        def update_history():
            status = esgf_process.status

            if status not in status_history:
                match = last_percent_regex.match(status)
                if match:
                    status_percent[0] = int(match.group(1))
                status_percent[0] = max(Percent.SENDING, status_percent[0])

                status_history.add(status)

                message = "ESGF status: " + status
                LOGGER.debug(message)
                self.update_status(message, status_percent[0], STATUS_RUNNING)

        update_history()

        while esgf_process.processing:
            update_history()
            time.sleep(sleep_time)

        update_history()

        return esgf_process.succeeded

    def _process_results(self, esgf_process, output_dir, expected_outputs):
        # type: (cwt.Process, AnyStr, Dict[AnyStr, AnyStr]) -> None
        """Process the result of the execution"""
        if not esgf_process.succeeded:
            message = "Process failed."
            LOGGER.debug(message)
            self.update_status(message, Percent.FINISHED, STATUS_FAILED)
            return

        message = "Process successful."
        LOGGER.debug(message)
        self.update_status(message, Percent.COMPUTE_DONE, STATUS_RUNNING)
        try:
            self._write_outputs(esgf_process.output.uri, output_dir, expected_outputs)
        except Exception:
            message = "Error while downloading files."
            LOGGER.exception(message)
            self.update_status(message, Percent.FINISHED, STATUS_FAILED)
            raise

    def _write_outputs(self, url, output_dir, expected_outputs):
        """Write the output netcdf url to a local drive"""
        message = "Downloading outputs."
        LOGGER.debug(message)
        self.update_status(message, Percent.COMPUTE_DONE, STATUS_RUNNING)

        nc_outputs = [v for v in expected_outputs.values() if v.lower().endswith(".nc")]
        if len(nc_outputs) > 1:
            raise NotImplemented("Multiple outputs are not implemented")

        LOGGER.debug("Downloading file: {}".format(url))

        # Standard Thredds naming convention?
        url = url.replace("/dodsC/", "/fileServer/")

        r = requests.get(url, allow_redirects=True, stream=True, verify=False)
        output_file_name = nc_outputs[0]

        with open(join(output_dir, output_file_name), "wb") as f:
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)

        message = "Download successful."
        LOGGER.debug(message)
        self.update_status(message, Percent.FINISHED, STATUS_SUCCEEDED)
