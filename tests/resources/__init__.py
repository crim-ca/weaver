import os
from typing import TYPE_CHECKING

from weaver import WEAVER_MODULE_DIR
from weaver.utils import load_file

if TYPE_CHECKING:
    from typing import Union

    from weaver.typedefs import JSON

RESOURCES_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), ""))
EXAMPLES_PATH = os.path.join(WEAVER_MODULE_DIR, "wps_restapi/examples")

GET_CAPABILITIES_TEMPLATE_URL = "{}?service=WPS&request=GetCapabilities&version=1.0.0"
DESCRIBE_PROCESS_TEMPLATE_URL = "{}?service=WPS&request=DescribeProcess&identifier={}&version=1.0.0"

# simulated remote server with remote processes (mocked with `responses` package)
TEST_REMOTE_SERVER_URL = "https://remote-server.com"
TEST_REMOTE_SERVER_WPS1_PROCESS_ID = "test-remote-process-wps1"
TEST_REMOTE_SERVER_WPS3_PROCESS_ID = "test-remote-process-wps3"
TEST_REMOTE_SERVER_WPS1_PROCESSES = [TEST_REMOTE_SERVER_WPS1_PROCESS_ID, "pavicstestdocs"]
TEST_REMOTE_SERVER_WPS1_GETCAP_XML = os.path.join(RESOURCES_PATH, "test_get_capabilities_wps1.xml")
TEST_REMOTE_SERVER_WPS1_GETCAP_URL = GET_CAPABILITIES_TEMPLATE_URL.format(
    TEST_REMOTE_SERVER_URL
)
TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_XML = os.path.join(RESOURCES_PATH, "test_describe_process_wps1.xml")
TEST_REMOTE_SERVER_WPS1_DESCRIBE_PROCESS_URL = DESCRIBE_PROCESS_TEMPLATE_URL.format(
    TEST_REMOTE_SERVER_URL, TEST_REMOTE_SERVER_WPS1_PROCESS_ID
)

TEST_HUMMINGBIRD_WPS1_URL = "https://remote-hummingbird.com/wps"
TEST_HUMMINGBIRD_WPS1_GETCAP_XML = os.path.join(RESOURCES_PATH, "wps_hummingbird_getcap.xml")
TEST_HUMMINGBIRD_WPS1_PROCESSES = [  # see 'TEST_HUMMINGBIRD_WPS1_GETCAP_XML' contents
    "ncdump", "spotchecker", "cchecker", "cfchecker", "cmor_checker", "qa_cfchecker", "qa_checker", "cdo_sinfo",
    "cdo_operation", "cdo_copy", "cdo_bbox", "cdo_indices", "ensembles", "cdo_inter_mpi"
]
TEST_HUMMINGBIRD_DESCRIBE_WPS1_XML = os.path.join(RESOURCES_PATH, "wps_hummingbird_ncdump_describe.xml")
TEST_HUMMINGBIRD_STATUS_WPS1_XML = os.path.join(RESOURCES_PATH, "wps_hummingbird_ncdump_status.xml")
TEST_INVALID_ESCAPE_CHARS_GETCAP_WPS1_XML = os.path.join(RESOURCES_PATH, "wps_invalid_escape_chars_getcap.xml")

TEST_EMU_WPS1_GETCAP_URL = "https://remote-emu.com/wps"
TEST_EMU_WPS1_GETCAP_XML = os.path.join(RESOURCES_PATH, "wps_caps_emu.xml")
TEST_EMU_WPS1_PROCESSES = [
    "binaryoperatorfornumbers", "wordcounter", "chomsky", "ultimate_question", "nap", "sleep",
    "bbox", "show_error", "dummyprocess", "hello", "inout"
]

WPS_ENUM_ARRAY_IO_ID = "subset_countries"
WPS_ENUM_ARRAY_IO_XML = os.path.join(RESOURCES_PATH, "wps_enum_array_io.xml")
WPS_LITERAL_COMPLEX_IO_ID = "ice_days"
WPS_LITERAL_COMPLEX_IO_XML = os.path.join(RESOURCES_PATH, "wps_literal_complex_io.xml")
WPS_LITERAL_VALUES_IO_ID = "ensemble_grid_point_cold_spell_duration_index"
WPS_LITERAL_VALUES_IO_XML = os.path.join(RESOURCES_PATH, "wps_literal_values_io.xml")
WPS_NO_INPUTS_ID = "pavicstestdocs"
WPS_NO_INPUTS_XML = os.path.join(RESOURCES_PATH, "wps_no_inputs.xml")
WPS_NO_INPUTS_URL = DESCRIBE_PROCESS_TEMPLATE_URL.format(
    TEST_REMOTE_SERVER_URL, WPS_NO_INPUTS_ID
)


def load_example(file_name):
    # type: (str) -> Union[JSON, str]
    file_path = os.path.join(EXAMPLES_PATH, file_name)
    return load_file(file_path)


def load_resource(file_name):
    # type: (str) -> Union[JSON, str]
    file_path = os.path.join(RESOURCES_PATH, file_name)
    return load_file(file_path)
