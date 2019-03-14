# noinspection PyProtectedMember
from weaver.processes.wps_package import null


# noinspection PyComparisonWithNone
def test_null():
    if null:
        raise AssertionError("null should not pass if clause")
    n = null.__class__
    assert null == n
    assert null == n()
    assert null.__class__ == n
    assert null.__class__ == n()
    assert null != None  # noqa
    assert null is not None
    assert bool(null) is False
