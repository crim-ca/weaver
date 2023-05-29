from typing import TYPE_CHECKING

from pywps import ComplexInput, LiteralOutput, ComplexOutput, Format
from pywps.app import Process
from pywps.inout import LiteralInput
from pywps.inout.literaltypes import AllowedValue
from pywps.validator.allowed_value import ALLOWEDVALUETYPE, RANGECLOSURETYPE
from pywps.validator.mode import MODE

from weaver.formats import ContentType
from weaver.processes.constants import WPS_INPUT, WPS_OUTPUT
from weaver.processes.convert import json2wps_io
from weaver.processes.types import ProcessType
from weaver.wps_restapi.swagger_definitions import WEAVER_SCHEMA_ECHO_PROCESS_URL

if TYPE_CHECKING:
    from typing import List, Optional

    from weaver.processes.wps_package import ANY_IO_Type

# TODO Change schema link (WEAVER_SCHEMA_ECHO_PROCESS_URL) to (WEAVER_SCHEMA_URL) before merging into main
DATA_FORMAT_COMPLEX = Format(mime_type=ContentType.APP_JSON,
                             extension=".json",
                             schema=f"{WEAVER_SCHEMA_ECHO_PROCESS_URL}/echo_process/complex_input_schema.json")

DATA_FORMAT_GEOMETRY = [Format(mime_type="application/gml+xml",
                               schema="http://schemas.opengis.net/gml/3.2.1/geometryBasic2d.xsd",
                               extension=".gml"),
                        Format(mime_type=ContentType.APP_JSON,
                               schema="http://schemas.opengis.net/ogcapi/features/part1/1.0"
                                      "/openapi/schemas/geometryGeoJSON.yaml",
                               extension=".json")]

DATA_FORMAT_IMAGES = [Format(mime_type="image/tiff", encoding="binary", extension=".tiff"),
                      Format(mime_type="application/jp2", encoding="binary", extension=".jp2")]

DATA_FORMAT_FEATURES_COLLECTION = [Format(mime_type="application/gml+xml",
                                          schema="http://schemas.opengis.net/gml/3.2.1/geometryBasic2d.xsd",
                                          extension=".gml"),
                                   Format(mime_type="application/vnd.google-earth.kml+xml",
                                          schema="https://schemas.opengis.net/kml/2.3/ogckml23.xsd",
                                          extension=".kml")]


class EchoProcess(Process):
    """
    Builtin process that implement the OGC echo process
    """

    type = ProcessType.WPS_LOCAL
    identifier = "echo_process"
    title = "Echo Process"
    version = "1.0.0"

    def __init__(self, *_, **__):
        # type: (*Any, **Any) -> None
        """
        Initialize the process with the definition of the OGC echo process.
        """
        inputs = [json2wps_io(i, WPS_INPUT) if isinstance(i, dict) else i for i in self.__get_inputs()]
        outputs = [json2wps_io(o, WPS_OUTPUT) if isinstance(o, dict) else o for o in self.__get_outputs()]

        super(EchoProcess, self).__init__(
            self._handler,
            self.identifier,
            title=self.title,
            abstract="This process accepts and number of input and simple echoes each input as an output.",
            version=self.version,
            inputs=inputs,
            outputs=outputs,
            store_supported=True,
            status_supported=True
        )

    @staticmethod
    def __get_inputs():
        string_input = LiteralInput("string_input",
                                    "String Literal Input Example",
                                    abstract="This is an example of a STRING literal input.",
                                    data_type="string",
                                    allowed_values=["Value1", "Value2", "Value3"],
                                    mode=MODE.SIMPLE)

        date_input = LiteralInput("date_input",
                                  "Date Literal Input Example",
                                  abstract="This is an example of a DATE literal input.",
                                  data_type="dateTime",
                                  mode=MODE.SIMPLE)

        measure_input = LiteralInput("measure_input",
                                     "Numerical Value with UOM Example",
                                     abstract="This is an example of a NUMERIC literal with an associated unit of "
                                              "measure.",
                                     data_type="float",
                                     mode=MODE.SIMPLE)

        double_input = LiteralInput("double_input",
                                    "Bounded Double Literal Input Example",
                                    abstract="This is an example of a DOUBLE literal input that is bounded between a "
                                             "value greater than 0 and 10.  The default value is 5.",
                                    data_type="float",
                                    default=5.0,
                                    allowed_values=AllowedValue(allowed_type=ALLOWEDVALUETYPE.RANGE,
                                                                minval=0,
                                                                maxval=10,
                                                                range_closure=RANGECLOSURETYPE.OPENCLOSED),
                                    mode=MODE.SIMPLE)

        array_input = LiteralInput("array_input",
                                   "Array Input Example",
                                   abstract="This is an example of a single process input that is an array of values. "
                                            " In this case, the input array would be interpreted as a single value "
                                            "and not as individual inputs.",
                                   data_type="integer",
                                   min_occurs=2,
                                   max_occurs=10,
                                   mode=MODE.SIMPLE)

        complex_object_input = ComplexInput("complex_object_input",
                                            "Complex Object Input Example",
                                            abstract="This is an example of a complex object input.",
                                            data_format=DATA_FORMAT_COMPLEX,
                                            supported_formats=[DATA_FORMAT_COMPLEX],
                                            mode=MODE.NONE)

        geometry_input = ComplexInput("geometry_input",
                                      "Geometry input",
                                      abstract="This is an example of a geometry input.  In this case the geometry "
                                               "can be expressed as a GML of GeoJSON geometry.",
                                      data_format=DATA_FORMAT_GEOMETRY[0],
                                      supported_formats=DATA_FORMAT_GEOMETRY,
                                      min_occurs=2,
                                      max_occurs=5,
                                      mode=MODE.NONE)

        images_input = ComplexInput("images_input",
                                    "Inline Images Value Input",
                                    abstract="This is an example of an image input.  In this case, the input is an "
                                             "array of up to 150 images that might, for example, be a set of tiles.  "
                                             "The oneOf[] conditional is used to indicate the acceptable image "
                                             "content types; GeoTIFF and JPEG 2000 in this case.  Each input image in "
                                             "the input array can be included inline in the execute request as a "
                                             "base64-encoded string or referenced using the link.yaml schema.  The "
                                             "use of a base64-encoded string is implied by the specification and does "
                                             "not need to be specified in the definition of the input.",
                                    data_format=DATA_FORMAT_IMAGES[0],
                                    supported_formats=DATA_FORMAT_IMAGES,
                                    min_occurs=1,
                                    max_occurs=150,
                                    mode=MODE.NONE)

        feature_collection_input = ComplexInput("feature_collection_input",
                                                title="Feature Collection Input Example",
                                                abstract="This is an example of an input that is a feature collection "
                                                         "that can be encoded in one of three ways. As a GeoJSON "
                                                         "feature collection, as a GML feature collection retrieved "
                                                         "from a WFS or as a KML document.",
                                                data_format=DATA_FORMAT_FEATURES_COLLECTION[0],
                                                supported_formats=DATA_FORMAT_FEATURES_COLLECTION)

        return [string_input, date_input, measure_input, double_input,
                array_input, complex_object_input, geometry_input,
                images_input, feature_collection_input]

    @staticmethod
    def __get_outputs():
        string_output = LiteralOutput("string_output",
                                      title="String Literal Output Example",
                                      data_type="string",
                                      mode=MODE.SIMPLE)

        date_output = LiteralOutput("date_output",
                                    title="Date Literal Output Example",
                                    data_type="dateTime",
                                    mode=MODE.SIMPLE)

        measure_output = LiteralOutput("measure_output",
                                       title="Numerical Output with UOM Example",
                                       data_type="float",
                                       mode=MODE.SIMPLE)

        double_output = LiteralOutput("double_output",
                                      title="Bounded Double Literal Ouput Example",
                                      data_type="float",
                                      mode=MODE.SIMPLE)

        array_output = LiteralOutput("array_output",
                                     title="Array Output Example",
                                     data_type="integer",
                                     mode=MODE.SIMPLE)

        complex_object_output = ComplexOutput("complex_object_output",
                                              title="Complex Object Output Example",
                                              supported_formats=[DATA_FORMAT_COMPLEX],
                                              data_format=DATA_FORMAT_COMPLEX,
                                              mode=MODE.NONE)

        geometry_output = ComplexOutput("geometry_output",
                                        title="Geometry output",
                                        supported_formats=DATA_FORMAT_GEOMETRY,
                                        data_format=DATA_FORMAT_GEOMETRY[0],
                                        mode=MODE.NONE)

        images_output = ComplexOutput("images_output",
                                      title="Inline Images Value Output",
                                      supported_formats=DATA_FORMAT_IMAGES,
                                      data_format=DATA_FORMAT_IMAGES[0],
                                      mode=MODE.NONE)

        feature_collection_output = ComplexOutput("feature_collection_output",
                                                  title="Feature Collection Output Example",
                                                  supported_formats=DATA_FORMAT_FEATURES_COLLECTION,
                                                  data_format=DATA_FORMAT_FEATURES_COLLECTION[0])

        return [string_output, date_output, measure_output, double_output,
                array_output, complex_object_output, geometry_output,
                images_output, feature_collection_output]

    def _handler(self, request, response):
        response.update_status(f"Echo process Output from process {self.identifier}...", 0)
        response.outputs["string_output"].data = request.inputs["string_input"][0].data
        response.outputs["date_output"].data = request.inputs["date_input"][0].data
        response.outputs["measure_output"].data = request.inputs["measure_input"][0].data
        response.outputs["double_output"].data = request.inputs["double_input"][0].data
        response.outputs["array_output"].data = [element.data for element in request.inputs["array_input"]]
        response.outputs["complex_object_output"].data = request.inputs["complex_object_input"][0].data
        response.outputs["geometry_output"].data = [element.data for element in request.inputs["geometry_input"]]
        response.outputs["images_output"].data = [element.data for element in request.inputs["images_input"]]
        response.outputs["feature_collection_output"].data = request.inputs["feature_collection_input"][0].data
        return response
