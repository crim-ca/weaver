from typing import TYPE_CHECKING

from pywps import ComplexInput
from pywps.app import Process
from pywps.inout import LiteralInput
from pywps.validator.mode import MODE

from weaver.processes.constants import WPS_INPUT, WPS_OUTPUT
from weaver.processes.convert import json2wps_field, json2wps_io
from weaver.processes.types import ProcessType

if TYPE_CHECKING:
    from typing import List, Optional

    from weaver.processes.wps_package import ANY_IO_Type


# FIXME: transform into official test EchoProcess (https://github.com/crim-ca/weaver/issues/379)
class WpsTestProcess(Process):
    """
    Test WPS process that implement the OGC echo process
    """

    type = ProcessType.TEST  # allows to map WPS class

    def __init__(self):
        # type: () -> None
        """
        Initialize the test process with the definition of the OGC echo process.
        """

        title = "Echo Process"
        version = "1.0.0"
        metadata = [{
            "description": "This process accepts and number of input and simple echoes each input as an output."
        }]
        inputs = [json2wps_io(i, WPS_INPUT) if isinstance(i, dict) else i for i in self.__get_inputs()]
        outputs = [json2wps_io(o, WPS_OUTPUT) if isinstance(o, dict) else o for o in self.__get_outputs()]
        metadata = [json2wps_field(meta, "metadata") for meta in metadata]

        super(WpsTestProcess, self).__init__(
            self._handler,
            title=title,
            version=version,
            inputs=inputs,
            outputs=outputs,
            metadata=metadata,
            store_supported=True,
            status_supported=True
        )

    @staticmethod
    def __get_inputs():
        string_input = LiteralInput("string-input",
                                    "String Literal Input Example",
                                    abstract="This is an example of a STRING literal input.",
                                    data_type="string",
                                    allowed_values=["Value1", "Value2", "Value3"],
                                    mode=MODE.SIMPLE)

        date_input = LiteralInput("date-input",
                                  "Date Literal Input Example",
                                  abstract="This is an example of a DATE literal input.",
                                  data_type="dateTime",
                                  mode=MODE.SIMPLE)

        measure_input = LiteralInput("measure-input",
                                     "Numerical Value with UOM Example",
                                     abstract="This is an example of a NUMERIC literal with an associated unit of "
                                              "measure.",
                                     data_type="float",
                                     mode=MODE.SIMPLE)

        double_input = LiteralInput("measure-input",
                                    "Numerical Value with UOM Example",
                                    abstract="This is an example of a NUMERIC literal with an associated unit of "
                                             "measure.",
                                    data_type="float",
                                    mode=MODE.SIMPLE)

        array_input = LiteralInput("array-input",
                                   "Array Input Example",
                                   abstract="This is an example of a single process input that is an array of values. "
                                            " In this case, the input array would be interpreted as a single value "
                                            "and not as individual inputs.",
                                   data_type="integer",
                                   min_occurs=2,
                                   max_occurs=10,
                                   mode=MODE.SIMPLE)

        complex_object_input = ComplexInput("complex-object-input",
                                            "Complex Object Input Example",
                                            abstract="This is an example of a complex object input.",
                                            data_format={
                                                "mime_type": "application/json",
                                                "encoding": "",
                                                "schema": {
                                                    "oneOf": [
                                                        {
                                                            "type": "string",
                                                            "contentMediaType": "application/json"
                                                        },
                                                        {
                                                            "type": "object",
                                                            "properties":
                                                                {
                                                                    "property1": {"type": "string"},
                                                                    "property2": {"type": "string",
                                                                                  "format": "uri"},
                                                                    "property3": {"type": "number"},
                                                                    "property4": {"type": "string",
                                                                                  "format": "date-time"},
                                                                    "property5": {"type": "boolean"}
                                                                },
                                                            "required": ["property1", "property5"]
                                                        }
                                                    ]
                                                },
                                                "extension": ""
                                            },
                                            mode=MODE.NONE)

        return [string_input, date_input, measure_input, double_input, array_input, complex_object_input]

    @staticmethod
    def __get_outputs():
        return []

    def _handler(self, request, response):
        response.update_status(f"WPS Test Output from process {self.identifier}...", 0)
        response.outputs["test_output"].data = request.inputs["test_input"][0].data
        return response
