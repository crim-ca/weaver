class DatabaseInterface(object):
    """Return the unique identifier of db type matching settings."""
    __slots__ = ['type']

    # noinspection PyUnusedLocal
    def __init__(self, registry):
        if not self.type:
            raise NotImplementedError("Database 'type' must be overridden in inheriting class.")
