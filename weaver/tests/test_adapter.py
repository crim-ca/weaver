from weaver.adapter import import_adapter, adapter_factory
from weaver.adapter.base import AdapterInterface
from weaver.adapter.default import DefaultAdapter


def test_import_adapter():
    adapter = import_adapter('weaver.adapter.default.DefaultAdapter')
    assert adapter is DefaultAdapter, "Expect {!s}, but got {!s}".format(DefaultAdapter, adapter)
    assert isinstance(adapter(), AdapterInterface), "Expect {!s}, but got {!s}".format(AdapterInterface, type(adapter))


def test_adapter_factory_default_explicit():
    settings = {'weaver.adapter': 'default'}
    adapter = adapter_factory(settings)
    assert isinstance(adapter, DefaultAdapter), "Expect {!s}, but got {!s}".format(DefaultAdapter, type(adapter))


def test_adapter_factory_none_specified():
    adapter = adapter_factory({})
    assert isinstance(adapter, DefaultAdapter), "Expect {!s}, but got {!s}".format(DefaultAdapter, type(adapter))


# noinspection PyAbstractClass
class TestAdapter(AdapterInterface):
    pass


# noinspection PyPep8Naming
def test_adapter_factory_TestAdapter():
    settings = {'weaver.adapter': TestAdapter.__module__ + '.' + TestAdapter.__name__}
    adapter = adapter_factory(settings)
    assert isinstance(adapter, TestAdapter), "Expect {!s}, but got {!s}".format(TestAdapter, type(adapter))
