import os

RESOURCES_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "resources"))

GET_CAPABILITIES_TEMPLATE_URL = "{}?service=WPS&request=GetCapabilities&version=1.0.0"
DESCRIBE_PROCESS_TEMPLATE_URL = "{}?service=WPS&request=DescribeProcess&identifier={}&version=1.0.0"

# simulated remote server with remote processes (mocked with `responses` package)
TEST_REMOTE_SERVER_URL = "https://remote-server.com"
TEST_REMOTE_PROCESS_WPS1_ID = "test-remote-process-wps1"
TEST_REMOTE_PROCESS_WPS3_ID = "test-remote-process-wps3"
TEST_REMOTE_PROCESS_GETCAP_WPS1_XML = os.path.join(RESOURCES_PATH, "test_get_capabilities_wps1.xml")
TEST_REMOTE_PROCESS_GETCAP_WPS1_URL = GET_CAPABILITIES_TEMPLATE_URL.format(
    TEST_REMOTE_SERVER_URL
)
TEST_REMOTE_PROCESS_DESCRIBE_WPS1_XML = os.path.join(RESOURCES_PATH, "test_describe_process_wps1.xml")
TEST_REMOTE_PROCESS_DESCRIBE_WPS1_URL = DESCRIBE_PROCESS_TEMPLATE_URL.format(
    TEST_REMOTE_SERVER_URL, TEST_REMOTE_PROCESS_WPS1_ID
)

WPS_CAPS_EMU_XML = os.path.join(RESOURCES_PATH, "wps_caps_emu.xml")
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
