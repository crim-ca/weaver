from twitcher.adapter import import_adapter, adapter_factory
from twitcher.adapter.base import AdapterInterface
from twitcher.adapter.default import DefaultAdapter


def test_import_adapter():
    adapter = import_adapter('twitcher.adapter.default.DefaultAdapter')
    assert adapter is DefaultAdapter, "Expect {!s}, but got {!s}".format(DefaultAdapter, adapter)
    assert isinstance(adapter(), AdapterInterface), "Expect {!s}, but got {!s}".format(AdapterInterface, type(adapter))


def test_adapter_factory_default_explicit():
    settings = {'twitcher.adapter': 'default'}
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
    settings = {'twitcher.adapter': TestAdapter.__module__ + '.' + TestAdapter.__name__}
    adapter = adapter_factory(settings)
    assert isinstance(adapter, TestAdapter), "Expect {!s}, but got {!s}".format(TestAdapter, type(adapter))
