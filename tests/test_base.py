import pytest

from weaver.base import Constants, ExtendedEnum


class DummyConstant(Constants):
    # pylint: disable=C0103,invalid-name  # on purpose for test
    T1 = "t1"
    T2 = "T2"
    t3 = "t3"
    t4 = "T4"
    T5 = "random5"  # ensure name is case-insensitive (not matched via the lowercase value)
    t6 = "RANDOM6"  # ensure name is case-insensitive (not matched via the uppercase value)


def test_constants_get_by_name_or_value_case_insensitive():
    assert DummyConstant.get("t1") == DummyConstant.T1
    assert DummyConstant.get("T1") == DummyConstant.T1
    assert DummyConstant.get("t2") == DummyConstant.T2
    assert DummyConstant.get("T2") == DummyConstant.T2
    assert DummyConstant.get("t3") == DummyConstant.t3
    assert DummyConstant.get("T3") == DummyConstant.t3
    assert DummyConstant.get("t4") == DummyConstant.t4
    assert DummyConstant.get("T4") == DummyConstant.t4
    assert DummyConstant.get("t5") == DummyConstant.T5
    assert DummyConstant.get("T5") == DummyConstant.T5
    assert DummyConstant.get("t6") == DummyConstant.t6
    assert DummyConstant.get("T6") == DummyConstant.t6
    assert DummyConstant.get("random5") == DummyConstant.T5
    assert DummyConstant.get("RANDOM5") == DummyConstant.T5
    assert DummyConstant.get("random6") == DummyConstant.t6
    assert DummyConstant.get("RANDOM6") == DummyConstant.t6


def test_constants_in_by_name_or_value():
    assert "t1" in DummyConstant
    assert "T1" in DummyConstant
    assert "t2" in DummyConstant
    assert "T2" in DummyConstant
    assert "t3" in DummyConstant
    assert "T3" in DummyConstant
    assert "t4" in DummyConstant
    assert "T4" in DummyConstant


def test_constants_immutable():
    with pytest.raises(TypeError):
        DummyConstant.T1 = "x"
    with pytest.raises(TypeError):
        setattr(DummyConstant, "T1", "x")
    with pytest.raises(TypeError):
        setattr(DummyConstant, "random", "x")


class DummyEnum(ExtendedEnum):
    # pylint: disable=C0103,invalid-name  # on purpose for test
    long = "LONG"
    SHORT = "short"


def test_enum_in_case_insensitive():
    assert "long" in DummyEnum
    assert "LONG" in DummyEnum
    assert DummyEnum.long in DummyEnum
    assert "short" in DummyEnum
    assert "SHORT" in DummyEnum
    assert DummyEnum.SHORT in DummyEnum


def test_enum_names():
    assert DummyEnum.names() == ["long", "SHORT"]


def test_enum_values():
    assert DummyEnum.values() == ["LONG", "short"]


def test_enum_titles():
    assert DummyEnum.titles() == ["Long", "Short"]


def test_enum_get_by_name_or_value():
    assert DummyEnum.get("LONG") == DummyEnum.long
    assert DummyEnum.get("long") == DummyEnum.long
    assert DummyEnum.get(DummyEnum.long) == DummyEnum.long
    assert DummyEnum.get("Long") is None
    assert DummyEnum.get("SHORT") == DummyEnum.SHORT
    assert DummyEnum.get("short") == DummyEnum.SHORT
    assert DummyEnum.get(DummyEnum.SHORT) == DummyEnum.SHORT
    assert DummyEnum.get("Short") is None
    assert DummyEnum.get("random") is None
    assert DummyEnum.get("random", default="other") == "other"
