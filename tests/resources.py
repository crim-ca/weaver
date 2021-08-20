import os

RESOURCES_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "resources"))

WPS_CAPS_EMU_XML = os.path.join(RESOURCES_PATH, "wps_caps_emu.xml")
WPS_ENUM_ARRAY_IO = os.path.join(RESOURCES_PATH, "wps_enum_array_io.xml")
WPS_LITERAL_COMPLEX_IO = os.path.join(RESOURCES_PATH, "wps_literal_complex_io.xml")

# simulated remote server with remote processes (mocked with `responses` package)
TEST_REMOTE_SERVER_URL = "https://remote-server.com"
TEST_REMOTE_PROCESS_WPS1_ID = "test-remote-process-wps1"
TEST_REMOTE_PROCESS_WPS3_ID = "test-remote-process-wps3"
TEST_REMOTE_PROCESS_GETCAP_WPS1_FILE = os.path.join(RESOURCES_PATH, "test_get_capabilities_wps1.xml")
TEST_REMOTE_PROCESS_GETCAP_WPS1_URL = "{}/wps?service=WPS&request=GetCapabilities&version=1.0.0".format(
    TEST_REMOTE_SERVER_URL
)
TEST_REMOTE_PROCESS_DESCRIBE_WPS1_FILE = os.path.join(RESOURCES_PATH, "test_describe_process_wps1.xml")
TEST_REMOTE_PROCESS_DESCRIBE_WPS1_URL = "{}/wps?service=WPS&request=DescribeProcess&identifier={}&version=1.0.0".format(
    TEST_REMOTE_SERVER_URL, TEST_REMOTE_PROCESS_WPS1_ID
)
