from typing import TYPE_CHECKING

from weaver.base import Constants


class Visibility(Constants):
    PUBLIC = "public"
    PRIVATE = "private"


if TYPE_CHECKING:
    from weaver.typedefs import Literal

    AnyVisibility = Literal[Visibility.PUBLIC, Visibility.PRIVATE]
