SORT_CREATED = "created"
SORT_FINISHED = "finished"
SORT_STATUS = "status"
SORT_PROCESS = "process"
SORT_SERVICE = "service"
SORT_USER = "user"
SORT_QUOTE = "quote"
SORT_PRICE = "price"
SORT_ID = "id"
SORT_ID_LONG = "identifier"  # long form employed by Processes in DB representation

PROCESS_SORT_VALUES = frozenset([
    SORT_ID,
    SORT_ID_LONG,  # will replace by short ID to conform with JSON representation
    SORT_PROCESS,  # since listing processes, can be an alias to ID
    SORT_CREATED,
])

JOB_SORT_VALUES = frozenset([
    SORT_CREATED,
    SORT_FINISHED,
    SORT_STATUS,
    SORT_PROCESS,
    SORT_SERVICE,
    SORT_USER,
])

QUOTE_SORT_VALUES = frozenset([
    SORT_ID,
    SORT_PROCESS,
    SORT_PRICE,
    SORT_CREATED,
])

BILL_SORT_VALUES = frozenset([
    SORT_ID,
    SORT_QUOTE,
    SORT_CREATED,
])
