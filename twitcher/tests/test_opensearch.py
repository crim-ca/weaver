import pytest
import mock

from pyramid.testing import DummyRequest

from twitcher.processes.opensearch import OpenSearch
from twitcher.store import DB_MEMORY, MemoryProcessStore
from twitcher.wps_restapi.processes import processes


def make_request(**kw):
    request = DummyRequest(**kw)
    if request.registry.settings is None:
        request.registry.settings = {}
    request.registry.settings['twitcher.url'] = "localhost"
    request.registry.settings['twitcher.db_factory'] = DB_MEMORY
    return request


@pytest.mark.online
@pytest.mark.slow
def test_query():
    params = {
        "startDate": "2018-01-30T00:00:00.000Z",
        "endDate": "2018-01-31T23:59:59.999Z",
        "bbox": "100.4,15.3,104.6,19.3",
    }
    test_parent_identifier = "EOP:IPT:Sentinel2"
    # test_parent_identifier = "EO:EUM:DAT:PROBA-V:ALDHSA"
    # test_parent_identifier = "deimos"

    url = "http://geo.spacebel.be/opensearch/description.xml?parentIdentifier=%s" % test_parent_identifier

    o = OpenSearch(url)
    for n, link in enumerate(o.query_datasets(params)):
        assert link.startswith(u'file:///')
        print(link)
        if n >= 0:
            break
