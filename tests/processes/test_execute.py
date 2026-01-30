"""
Unit tests for utility methods of :mod:`weaver.processes.execute`.

For more in-depth execution tests, see ``tests.functional``.
"""
import dataclasses
import uuid
from typing import TYPE_CHECKING, List, cast

import mock
import pytest
from owslib.wps import BoundingBoxDataInput, ComplexDataInput, Input, Process

from weaver.datatype import Job
from weaver.formats import ContentEncoding, ContentType
from weaver.processes.constants import WPS_BOUNDINGBOX_DATA, WPS_COMPLEX_DATA, WPS_LITERAL, WPS_CategoryType
from weaver.processes.execution import parse_wps_inputs
from weaver.wps_restapi.swagger_definitions import OGC_API_PROC_BBOX_CRS

if TYPE_CHECKING:
    from weaver.processes.convert import OWS_Input_Type
    from weaver.typedefs import JSON


@dataclasses.dataclass
class MockInputDefinition:
    # pylint: disable=C0103  # must use the names employed by OWSLib, even if not standard snake case
    # override Input to skip XML parsing
    identifier: str = "test"
    dataType: WPS_CategoryType = None


class MockProcess:
    # pylint: disable=C0103  # must use the names employed by OWSLib, even if not standard snake case
    # override Process to skip XML parsing
    def __init__(self, inputs: List[Input]) -> None:
        self.identifier = "test"
        self.dataInputs = inputs


@mock.patch(
    # avoid error on database connection not established
    "weaver.processes.execution.log_and_save_update_status_handler",
    lambda *_, **__: lambda *_a, **__kw: None,
)
@pytest.mark.parametrize(
    ["input_data", "input_definition", "expect_input"],
    [
        (
            {"value": None},
            MockInputDefinition(dataType=WPS_LITERAL),
            None,
        ),
        (
            {"value": 1},
            MockInputDefinition(dataType=WPS_LITERAL),
            "1",
        ),
        (
            {"bbox": [1, 2, 3, 4], "crs": OGC_API_PROC_BBOX_CRS},
            MockInputDefinition(dataType=WPS_BOUNDINGBOX_DATA),
            BoundingBoxDataInput(
                [1, 2, 3, 4],
                crs=OGC_API_PROC_BBOX_CRS,
                dimensions=2,
            )
        ),
        (
            {"href": "https://test.com/some-file.json", "mediaType": ContentType.APP_JSON},
            MockInputDefinition(dataType=WPS_COMPLEX_DATA),
            ComplexDataInput(
                "https://test.com/some-file.json",
                mimeType=ContentType.APP_JSON,
                encoding=None,
                schema=None,
            ),
        ),
        (
            {
                "href": "https://test.com/some-img.tif",
                "mediaType": ContentType.IMAGE_GEOTIFF,
                "encoding": ContentEncoding.BASE64,
            },
            MockInputDefinition(dataType=WPS_COMPLEX_DATA),
            ComplexDataInput(
                "https://test.com/some-img.tif",
                mimeType=ContentType.IMAGE_GEOTIFF,
                encoding=ContentEncoding.BASE64,
                schema=None,
            ),
        ),
    ]
)
def test_parse_wps_inputs(input_data, input_definition, expect_input):
    # type: (JSON, MockInputDefinition, OWS_Input_Type) -> None
    input_def = cast(Input, input_definition)
    proc = cast(Process, MockProcess([input_def]))
    job = Job(task_id=uuid.uuid4())
    input_data.update({"id": input_def.identifier})
    job.inputs = [input_data]
    result_inputs = parse_wps_inputs(proc, job)
    if expect_input is None:
        assert result_inputs == []  # pylint: disable=C1803  # not check only if empty, we want to check the type also!
    else:
        result_input = result_inputs[0][1]
        if not isinstance(expect_input, str):
            assert isinstance(result_input, type(expect_input))
            fields = list(filter(
                lambda attr: not attr.startswith("__") and not callable(getattr(expect_input, attr)),
                dir(expect_input))
            )
            assert len(fields)
            for field in fields:
                expect_field = getattr(expect_input, field)
                result_field = getattr(result_input, field)
                assert expect_field == result_field, f"Field [{field}] did not match"
        else:
            assert result_input == expect_input
