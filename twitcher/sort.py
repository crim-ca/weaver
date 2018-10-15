SORT_CREATED = 'created'
SORT_FINISHED = 'finished'
SORT_STATUS = 'status'
SORT_PROCESS = 'process'
SORT_SERVICE = 'service'
SORT_USER = 'user'
SORT_QUOTE = 'quote'
SORT_PRICE = 'price'
SORT_ID = 'id'

job_sort_values = frozenset([
    SORT_CREATED,
    SORT_FINISHED,
    SORT_STATUS,
    SORT_PROCESS,
    SORT_SERVICE,
    SORT_USER,
])

quote_sort_values = frozenset([
    SORT_ID,
    SORT_PROCESS,
    SORT_PRICE,
    SORT_CREATED,
])

bill_sort_values = frozenset([
    SORT_ID,
    SORT_QUOTE,
    SORT_CREATED,
])
