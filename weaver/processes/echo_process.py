from typing import TYPE_CHECKING

from pywps import ComplexInput, LiteralOutput, ComplexOutput
from pywps.app import Process
from pywps.inout import LiteralInput
from pywps.validator.mode import MODE

from weaver.processes.constants import WPS_INPUT, WPS_OUTPUT
from weaver.processes.convert import json2wps_field, json2wps_io
from weaver.processes.types import ProcessType

if TYPE_CHECKING:
    from typing import List, Optional

    from weaver.processes.wps_package import ANY_IO_Type

DATA_FORMAT_COMPLEX = {
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
}

DATA_FORMAT_GEOMETRY = {
    "mime_type": "application/gml+xml; version=3.2",
    "encoding": "",
    "schema": {
        "type": "array",
        "items": {
            "oneOf": [
                {
                    "type": "string",
                    "contentMediaType": "application/gml+xml; version=3.2",
                    "contentSchema": "http://schemas.opengis.net/gml/3.2.1"
                                     "/geometryBasic2d.xsd"
                },
                {
                    "type": "string",
                    "contentMediaType": "application/json",
                    "contentSchema": "http://schemas.opengis.net/ogcapi"
                                     "/features/part1/1.0/openapi/schemas"
                                     "/geometryGeoJSON.yaml"
                }
            ],
            "allOf": [
                {
                    "format": "geojson-geometry"
                },
                {
                    "$ref": "http://schemas.opengis.net/ogcapi/features/part1/1"
                            ".0/openapi/schemas/geometryGeoJSON.yaml"
                }
            ]
        }
    }
}

DATA_FORMAT_IMAGES = {
    "mime_type": "application/tiff; application=geotiff",
    "encoding": "binary",
    "schema": {
        "oneOf": [
            {
                "type": "string",
                "contentEncoding": "binary",
                "contentMediaType": "application/tiff; application=geotiff"
            },
            {
                "type": "string",
                "contentEncoding": "binary",
                "contentMediaType": "application/jp2"
            }
        ]
    }
}

DATA_FORMAT_FEATURES_COLLECTION = {
    "mime_type": "application/json",
    "encoding": "",
    "schema": {
        "oneOf": [
            {
                "type": "string",
                "contentMediaType": "application/gml+xml; version=3.2"
            },
            {
                "type": "string",
                "contentSchema": "https://schemas.opengis.net/kml/2.3"
                                 "/ogckml23.xsd",
                "contentMediaType": "application/vnd.google-earth.kml"
                                    "+xml"
            },
            {
                "allOf": [
                    {
                        "format": "geojson-feature-collection"
                    },
                    {
                        "$ref": "https://geojson.org/schema"
                                "/FeatureCollection.json"
                    }
                ]
            }
        ]
    }
}


class EchoProcess(Process):
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

        super(EchoProcess, self).__init__(
            "echo-process",
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
                                      data_format=DATA_FORMAT_GEOMETRY,
                                      supported_formats=[DATA_FORMAT_GEOMETRY],
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
                                    data_format=DATA_FORMAT_IMAGES,
                                    supported_formats=[DATA_FORMAT_IMAGES],
                                    min_occurs=1,
                                    max_occurs=150,
                                    mode=MODE.NONE)

        feature_collection_input = ComplexInput("feature_collection_input",
                                                title="Feature Collection Input Example",
                                                abstract="This is an example of an input that is a feature collection "
                                                         "that can be encoded in one of three ways. As a GeoJSON "
                                                         "feature collection, as a GML feature collection retrieved "
                                                         "from a WFS or as a KML document.",
                                                data_format=DATA_FORMAT_FEATURES_COLLECTION,
                                                supported_formats=[DATA_FORMAT_FEATURES_COLLECTION])

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
                                              data_format=DATA_FORMAT_COMPLEX,
                                              mode=MODE.NONE)

        geometry_output = ComplexOutput("geometry_output",
                                        title="Geometry output",
                                        data_format=DATA_FORMAT_GEOMETRY,
                                        mode=MODE.NONE)

        images_output = ComplexOutput("images_output",
                                      title="Inline Images Value Output",
                                      data_format=DATA_FORMAT_IMAGES,
                                      mode=MODE.NONE)

        feature_collection_output = ComplexOutput("feature_collection_output",
                                                  title="Feature Collection Output Example",
                                                  data_format=DATA_FORMAT_FEATURES_COLLECTION)

        return [string_output, date_output, measure_output, double_output,
                array_output, complex_object_output, geometry_output,
                images_output, feature_collection_output]

    def _handler(self, request, response):
        response.update_status(f"Echo process Output from process {self.identifier}...", 0)
        response.outputs["string_output"].data = request.inputs["string_input"].data
        response.outputs["date_output"].data = request.inputs["date_input"].data
        response.outputs["measure_output"].data = request.inputs["measure_input"].data
        response.outputs["double_output"].data = request.inputs["double_input"].data
        response.outputs["array_output"].data = request.inputs["array_input"].data
        response.outputs["complex_object_output"].data = request.inputs["complex_object_input"].data
        response.outputs["geometry_output"].data = request.inputs["geometry_input"].data
        response.outputs["images_output"].data = request.inputs["images_input"].data
        response.outputs["feature_collection_output"].data = request.inputs["feature_collection_input"].data
        return response
