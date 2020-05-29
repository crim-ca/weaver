from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from weaver.typedefs import AnySettingsContainer


class DatabaseInterface(object):
    """Return the unique identifier of db type matching settings."""
    __slots__ = ["type"]

    def __init__(self, container):   # noqa: E811
        # type: (AnySettingsContainer) -> None
        if not self.type:  # pylint: disable=E1101,no-member
            raise NotImplementedError("Database 'type' must be overridden in inheriting class.")
