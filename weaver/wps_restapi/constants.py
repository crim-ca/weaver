from typing import TYPE_CHECKING

from weaver.base import Constants


class JobInputsOutputsSchema(Constants):
    """
    Schema selector to represent a :term:`Job` output results.
    """
    OGC_STRICT = "ogc+strict"
    OLD_STRICT = "old+strict"
    OGC = "ogc"
    OLD = "old"


if TYPE_CHECKING:
    from weaver.typedefs import Literal

    JobInputsOutputsSchemaType = Literal[
        JobInputsOutputsSchema.OGC_STRICT,
        JobInputsOutputsSchema.OLD_STRICT,
        JobInputsOutputsSchema.OGC,
        JobInputsOutputsSchema.OLD
    ]
