import abc
from typing import TYPE_CHECKING

from weaver.store.base import StoreInterface

if TYPE_CHECKING:
    from weaver.typedefs import AnySettingsContainer, JSON, Type, Union

    StoreSelector = Union[Type[StoreInterface], StoreInterface, str]


class DatabaseInterface(metaclass=abc.ABCMeta):
    """Return the unique identifier of db type matching settings."""
    __slots__ = ["type"]

    def __init__(self, _):
        # type: (AnySettingsContainer) -> None
        if not self.type:  # pylint: disable=E1101,no-member
            raise NotImplementedError("Database 'type' must be overridden in inheriting class.")

    @staticmethod
    def _get_store_type(store_type):
        # type: (StoreSelector) -> str
        if isinstance(store_type, StoreInterface):
            return store_type.type
        if isinstance(store_type, type) and issubclass(store_type, StoreInterface):
            return store_type.type
        if isinstance(store_type, str):
            return store_type
        raise TypeError("Unsupported store type selector: [{}] ({})".format(store_type, type(store_type)))

    @abc.abstractmethod
    def get_store(self, store_type, *store_args, **store_kwargs):
        raise NotImplementedError

    @abc.abstractmethod
    def reset_store(self, store_type):
        # type: (StoreSelector) -> None
        raise NotImplementedError

    @abc.abstractmethod
    def get_session(self):
        raise NotImplementedError

    @abc.abstractmethod
    def get_information(self):
        # type: (...) -> JSON
        """
        Obtain information about the database.

        The implementing class should provide JSON serializable metadata.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def is_ready(self):
        # type: (...) -> bool
        raise NotImplementedError

    @abc.abstractmethod
    def run_migration(self):
        # type: (...) -> None
        raise NotImplementedError
