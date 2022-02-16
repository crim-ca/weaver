from typing import TYPE_CHECKING

from weaver.base import Constants


class QuoteStatus(Constants):
    SUBMITTED = "submitted"
    PROCESSING = "processing"
    COMPLETED = "completed"


if TYPE_CHECKING:
    from weaver.typedefs import Literal

    AnyQuoteStatus = Literal[
        QuoteStatus.SUBMITTED,
        QuoteStatus.PROCESSING,
        QuoteStatus.COMPLETED,
    ]
