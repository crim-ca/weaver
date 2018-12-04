EXECUTE_MODE_AUTO = 'auto'
EXECUTE_MODE_ASYNC = 'async'
EXECUTE_MODE_SYNC = 'sync'

execute_mode_options = frozenset([
    EXECUTE_MODE_AUTO,
    EXECUTE_MODE_ASYNC,
    EXECUTE_MODE_SYNC,
])

EXECUTE_CONTROL_OPTION_ASYNC = 'execute-async'
EXECUTE_CONTROL_OPTION_SYNC = 'execute-sync'

execute_control_options = frozenset([
    EXECUTE_CONTROL_OPTION_ASYNC,
    EXECUTE_CONTROL_OPTION_SYNC,
])

EXECUTE_RESPONSE_RAW = 'raw'
EXECUTE_RESPONSE_DOCUMENT = 'document'

execute_response_options = frozenset([
    EXECUTE_RESPONSE_RAW,
    EXECUTE_RESPONSE_DOCUMENT,
])

EXECUTE_TRANSMISSION_MODE_VALUE = 'value'
EXECUTE_TRANSMISSION_MODE_REFERENCE = 'reference'

execute_transmission_mode_options = frozenset([
    EXECUTE_TRANSMISSION_MODE_VALUE,
    EXECUTE_TRANSMISSION_MODE_REFERENCE,
])
