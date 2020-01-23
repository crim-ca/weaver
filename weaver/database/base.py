class DatabaseInterface(object):
    """Return the unique identifier of db type matching settings."""
    __slots__ = ["type"]

    def __init__(self, registry):   # noqa: E811
        # FIXME: remove pylint disable when https://github.com/PyCQA/pylint/issues/3364 is fixed
        # pylint: disable=E1101,no-member
        if not self.type:
            raise NotImplementedError("Database 'type' must be overridden in inheriting class.")
