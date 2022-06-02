"""
Definitions of base classes employed across multiple modules to avoid circular import errors.
"""
import abc
import enum
import inspect
from typing import TYPE_CHECKING, NewType

if TYPE_CHECKING:
    from typing import Any, Callable, Dict, List, Optional, Union

    from weaver.typedefs import AnyKey

# pylint: disable=E1120,no-value-for-parameter


class _Const(type):
    def __setattr__(cls, key, value):
        raise TypeError(f"Constant [{cls.__name__}.{key}] is not modifiable!")

    def __setitem__(cls, key, value):
        _Const.__setattr__(cls, key, value)

    def __contains__(cls, item):
        return cls.get(item) is not None

    @abc.abstractmethod
    def get(cls, key):
        raise NotImplementedError


class Constants(object, metaclass=_Const):
    """
    Constants container that provides similar functionalities to :class:`ExtendedEnum` without explicit Enum membership.
    """

    @classmethod
    def __members__(cls):
        members = set(cls.__dict__) - set(object.__dict__)
        members = [member for member in members if not inspect.ismethod(getattr(cls, member))]
        return [member for member in members if not isinstance(member, str) or not member.startswith("_")]

    @classmethod
    def get(cls, key_or_value, default=None):
        # type: (Union[AnyKey, EnumType], Optional[Any]) -> Any
        if isinstance(key_or_value, str):
            upper_key = key_or_value.upper()
            lower_key = key_or_value.lower()
        else:
            upper_key = lower_key = key_or_value
        if upper_key in cls.names():
            return cls.__dict__.get(upper_key, default)
        if lower_key in cls.names():
            return cls.__dict__.get(lower_key, default)
        if key_or_value in cls.values():
            return key_or_value
        return default

    @classmethod
    def docs(cls):
        # type: () -> Dict[str, Optional[str]]
        """
        Retrieves the documentation string applied on the attribute.

        Employ :class:`classproperty` to define the attributes.
        """
        return {
            # consider only classproperty items because direct attributes will pick up base type literal docstrings
            member: cls.__dict__[member].__doc__ if isinstance(cls.__dict__[member], classproperty) else None
            for member in cls.__members__()
        }

    @classmethod
    def names(cls):
        # type: () -> List[str]
        """
        Returns the member names assigned to corresponding enum elements.
        """
        return list(cls.__members__())

    @classmethod
    def values(cls):
        # type: () -> List[AnyKey]
        """
        Returns the literal values assigned to corresponding enum elements.
        """
        return [getattr(cls, member) for member in cls.__members__()]


class classproperty(property):  # pylint: disable=C0103,invalid-name
    """
    Mimics :class:`property` decorator, but applied onto ``classmethod`` in backward compatible way.

    .. note::
        This decorator purposely only supports getter attribute to define unmodifiable class properties.

    .. seealso::
        https://stackoverflow.com/a/5191224
    """

    def __init__(self,
                 fget=None,     # type: Optional[Callable[[object], Any]]
                 fset=None,     # type: Optional[Callable[[object, Any], None]]
                 fdel=None,     # type: Optional[Callable[[object], None]]
                 doc="",        # type: str
                 ):             # type: (...) -> None
        super(classproperty, self).__init__(fget=fget, fset=fset, fdel=fdel, doc=doc)
        self.__doc__ = inspect.cleandoc(doc)

    def __get__(self, cls, owner):  # noqa
        return classmethod(self.fget).__get__(None, owner)()


class _EnumMeta(enum.EnumMeta):
    def __contains__(cls, member):
        """
        Allows checking if item is member of the enum by value without having to manually convert to enum member.
        """
        if isinstance(member, cls):
            return super(_EnumMeta, cls).__contains__(member)
        return cls.get(member) is not None

    @abc.abstractmethod
    def get(cls, key):
        raise NotImplementedError


class ExtendedEnum(enum.Enum, metaclass=_EnumMeta):
    """
    Utility :class:`enum.Enum` methods.

    Create an extended enum with these utilities as follows.

    .. code-block:: python

        class CustomEnum(ExtendedEnum):
            ItemA = "A"
            ItemB = "B"

    .. warning::
        Must not define any enum value here to allow inheritance by subclasses.
    """

    @classmethod
    def names(cls):
        # type: () -> List[str]
        """
        Returns the member names assigned to corresponding enum elements.
        """
        return list(cls.__members__)

    @classmethod
    def values(cls):
        # type: () -> List[AnyKey]
        """
        Returns the literal values assigned to corresponding enum elements.
        """
        return [m.value for m in cls.__members__.values()]                      # pylint: disable=E1101

    @classmethod
    def get(cls, key_or_value, default=None):
        # type: (Union[AnyKey, EnumType], Optional[Any]) -> Optional[EnumType]
        """
        Finds an enum entry by defined name or its value.

        Returns the entry directly if it is already a valid enum.
        """
        # Python 3.8 disallow direct check of 'str' in 'enum'
        members = [member for member in cls]
        if key_or_value in members:                                             # pylint: disable=E1133
            return key_or_value
        for m_key, m_val in cls.__members__.items():                            # pylint: disable=E1101
            if key_or_value == m_key or key_or_value == m_val.value:            # pylint: disable=R1714
                return m_val
        return default

    @classmethod
    def titles(cls):
        # type: () -> List[str]
        """
        Returns the title representation of all enum elements.
        """
        return list(member.title for member in cls.__members__.values())

    @property
    def title(self):
        # type: () -> str
        """
        Returns the title representation of the enum element.

        Title use the original enum element name with capitalization considering underscores for separate words.
        """
        return self.name.title().replace("_", "")  # pylint: disable=E1101,no-member


if TYPE_CHECKING:
    EnumType = NewType("EnumType", ExtendedEnum)
