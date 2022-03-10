from typing import TYPE_CHECKING

from weaver.base import Constants


class JobOutputsSchema(Constants):
    """
    Schema selector to represent a :term:`Job` output results.
    """
    OGC_STRICT = "ogc+strict"
    OLD_STRICT = "old+strict"
    OGC = "ogc"
    OLD = "old"


if TYPE_CHECKING:
    from weaver.typedefs import Literal

    JobOutputsSchemaType = Literal[
        JobOutputsSchema.OGC_STRICT,
        JobOutputsSchema.OLD_STRICT,
        JobOutputsSchema.OGC,
        JobOutputsSchema.OLD
    ]
