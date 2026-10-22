import pytest
from pywps import Format
from pywps.exceptions import InvalidParameterValue
from pywps.inout.inputs import ComplexInput

from weaver.formats import ContentType
from weaver.wps.service import WorkerService


def make_input(media_type):
    fmt = Format(media_type, extension=".tif")
    fmt.default = True  # attribute added by Weaver when resolving process formats
    return ComplexInput("file", "file", supported_formats=[fmt], min_occurs=1, max_occurs=1)


@pytest.mark.format
@pytest.mark.parametrize(
    ["official_type", "legacy_type"],
    [
        (ContentType.IMAGE_OGC_GEOTIFF, ContentType.APP_OGC_GEOTIFF),
        (ContentType.IMAGE_JPEG2000, ContentType.APP_JPEG2000),
    ]
)
def test_create_complex_inputs_legacy_media_type(official_type, legacy_type):
    service = WorkerService.__new__(WorkerService)
    source = make_input(official_type)
    data = {"mimeType": legacy_type, "href": "https://example.com/data.tif", "method": "GET"}
    inputs = service.create_complex_inputs(source, [data])
    assert len(inputs) == 1
    assert inputs[0].data_format.mime_type == legacy_type
    assert [fmt.mime_type for fmt in source.supported_formats] == [official_type]  # definition not modified

    data["mimeType"] = ContentType.IMAGE_PNG
    with pytest.raises(InvalidParameterValue):
        service.create_complex_inputs(source, [data])
