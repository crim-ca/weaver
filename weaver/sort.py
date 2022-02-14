from weaver.base import Constants, ExtendedEnum


class Sort(Constants):
    CREATED = "created"
    FINISHED = "finished"
    STATUS = "status"
    PROCESS = "process"
    SERVICE = "service"
    USER = "user"
    QUOTE = "quote"
    PRICE = "price"
    ID = "id"
    ID_LONG = "identifier"  # long form employed by Processes in DB representation


class SortMethods(ExtendedEnum):
    PROCESS = frozenset([
        Sort.ID,
        Sort.ID_LONG,  # will replace by short ID to conform with JSON representation
        Sort.PROCESS,  # since listing processes, can be an alias to ID
        Sort.CREATED,
    ])
    JOB = frozenset([
        Sort.CREATED,
        Sort.FINISHED,
        Sort.STATUS,
        Sort.PROCESS,
        Sort.SERVICE,
        Sort.USER,
    ])
    QUOTE = frozenset([
        Sort.ID,
        Sort.PROCESS,
        Sort.PRICE,
        Sort.CREATED,
    ])

    BILL = frozenset([
        Sort.ID,
        Sort.QUOTE,
        Sort.CREATED,
    ])
