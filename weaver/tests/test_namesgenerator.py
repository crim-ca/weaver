from weaver.namesgenerator import get_random_name, get_sane_name, assert_sane_name
import pytest


def test_get_random_name():
    name = get_random_name()
    assert len(name) > 3
    assert '_' in name


def test_get_random_name_retry():
    name = get_random_name(retry=True)
    assert len(name) > 3
    assert int(name[-1]) >= 0


def test_get_sane_name_replace():
    kw = {'assert_invalid': False, 'replace_invalid': True}
    assert get_sane_name("Hummingbird", **kw) == "hummingbird"
    assert get_sane_name("MapMint Demo Instance", **kw) == "mapmint_demo_instance"
    assert get_sane_name(None, **kw) is None
    assert get_sane_name("12", **kw) is None
    assert get_sane_name(" ab c ", **kw) == "ab_c"
    assert get_sane_name("a_much_to_long_name_for_this_test", **kw) == "a_much_to_long_name_for_t"


def test_assert_sane_name():
    test_cases_invalid = [
        None,
        "12",   # too short
        " ab c ",
        "MapMint Demo Instance",
        "double--dashes_not_ok",
        "-start_dash_not_ok",
        "end_dash_not_ok-",
        "no_exclamation!point",
        "no_interrogation?point",
        "no_slashes/allowed",
        "no_slashes\\allowed",
    ]
    for test in test_cases_invalid:
        with pytest.raises(ValueError):
            assert_sane_name(test)

    test_cases_valid = [
        "Hummingbird",
        "short",
        "a_very_long_name_for_this_test_is_ok_if_maxlen_is_none",
        "AlTeRnAtInG_cApS"
        "middle-dashes-are-ok",
        "underscores_also_ok",
    ]
    for test in test_cases_valid:
        assert_sane_name(test)
