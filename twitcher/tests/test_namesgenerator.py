from twitcher.namesgenerator import get_random_name
from twitcher.namesgenerator import get_sane_name


def test_get_random_name():
    name = get_random_name()
    assert len(name) > 3
    assert '_' in name


def test_get_random_name_retry():
    name = get_random_name(retry=True)
    assert len(name) > 3
    assert int(name[-1]) >= 0


def test_get_sane_name():
    assert get_sane_name("Hummingbird") == "hummingbird"
    assert get_sane_name("MapMint Demo Instance") == "mapmint_demo_instance"
    assert get_sane_name(None) is None
    assert get_sane_name("12") is None
    assert get_sane_name(" ab c ") == "ab_c"
    assert get_sane_name("a_much_to_long_name_for_this_test") == "a_much_to_long_name_for_t"
