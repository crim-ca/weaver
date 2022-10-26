from typing import TYPE_CHECKING

from weaver.base import Constants


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
    VERSION = "version"


class SortMethods(Constants):
    PROCESS = frozenset([
        Sort.ID,
        Sort.ID_LONG,  # will replace by short ID to conform with JSON representation
        Sort.PROCESS,  # since listing processes, can be an alias to ID
        Sort.CREATED,
        Sort.VERSION,
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


if TYPE_CHECKING:
    from typing import Union
    from typing_extensions import Literal

    AnySortType = Literal[
        Sort.CREATED,
        Sort.FINISHED,
        Sort.STATUS,
        Sort.PROCESS,
        Sort.SERVICE,
        Sort.USER,
        Sort.QUOTE,
        Sort.PRICE,
        Sort.ID,
        Sort.ID_LONG,
        Sort.VERSION,
    ]

    AnySortMethodsType = Union[
        SortMethods.PROCESS,
        SortMethods.JOB,
        SortMethods.QUOTE,
        SortMethods.BILL,
    ]
