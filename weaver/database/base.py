import abc
from typing import TYPE_CHECKING, overload

from weaver.store.base import StoreInterface

if TYPE_CHECKING:
    from typing import Any, Type, Union

    from weaver.store.base import (
        StoreBills,
        StoreBillsType,
        StoreJobs,
        StoreJobsType,
        StoreProcesses,
        StoreProcessesType,
        StoreQuotes,
        StoreQuotesType,
        StoreServices,
        StoreServicesType,
        StoreTypeName,
        StoreVault,
        StoreVaultType
    )
    from weaver.typedefs import AnySettingsContainer, JSON

    AnyStore = Union[
        StoreBills,
        StoreJobs,
        StoreProcesses,
        StoreQuotes,
        StoreServices,
        StoreVault
    ]
    StoreBillsSelector = Union[Type[StoreBills], StoreBillsType]
    StoreJobsSelector = Union[Type[StoreJobs], StoreJobsType]
    StoreProcessesSelector = Union[Type[StoreProcesses], StoreProcessesType]
    StoreQuotesSelector = Union[Type[StoreQuotes], StoreQuotesType]
    StoreServicesSelector = Union[Type[StoreServices], StoreServicesType]
    StoreVaultSelector = Union[Type[StoreVault], StoreVaultType]
    StoreSelector = Union[
        StoreBillsSelector,
        StoreJobsSelector,
        StoreProcessesSelector,
        StoreQuotesSelector,
        StoreServicesSelector,
        StoreVaultSelector,
    ]


class DatabaseInterface(metaclass=abc.ABCMeta):
    """
    Return the unique identifier of db type matching settings.
    """
    __slots__ = ["type"]

    def __init__(self, _):
        # type: (AnySettingsContainer) -> None
        if not self.type:  # pylint: disable=E1101,no-member
            raise NotImplementedError("Database 'type' must be overridden in inheriting class.")

    @staticmethod
    def _get_store_type(store_type):
        # type: (Union[StoreSelector, Type[StoreInterface], StoreInterface]) -> StoreTypeName
        if isinstance(store_type, StoreInterface):
            return store_type.type
        if isinstance(store_type, type) and issubclass(store_type, StoreInterface):
            return store_type.type
        if isinstance(store_type, str):
            return store_type  # type: ignore
        raise TypeError(f"Unsupported store type selector: [{store_type}] ({type(store_type)})")

    @overload
    def get_store(self, store_type):
        # type: (StoreBillsSelector) -> StoreBills
        ...

    @overload
    def get_store(self, store_type):
        # type: (StoreQuotesSelector) -> StoreQuotes
        ...

    @overload
    def get_store(self, store_type):
        # type: (StoreJobsSelector) -> StoreJobs
        ...

    @overload
    def get_store(self, store_type):
        # type: (StoreProcessesSelector) -> StoreProcesses
        ...

    @overload
    def get_store(self, store_type):
        # type: (StoreServicesSelector) -> StoreServices
        ...

    @overload
    def get_store(self, store_type):
        # type: (StoreVaultSelector) -> StoreVault
        ...

    @overload
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (StoreBillsSelector, *Any, **Any) -> StoreBills
        ...

    @overload
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (StoreQuotesSelector, *Any, **Any) -> StoreQuotes
        ...

    @overload
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (StoreJobsSelector, *Any, **Any) -> StoreJobs
        ...

    @overload
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (StoreProcessesSelector, *Any, **Any) -> StoreProcesses
        ...

    @overload
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (StoreServicesSelector, *Any, **Any) -> StoreServices
        ...

    @overload
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (StoreVaultSelector, *Any, **Any) -> StoreVault
        ...

    @abc.abstractmethod
    def get_store(self, store_type, *store_args, **store_kwargs):
        # type: (StoreSelector, *Any, **Any) -> AnyStore
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
