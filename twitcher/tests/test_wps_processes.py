import mock

from pyramid.testing import DummyRequest

from twitcher.store import DB_MEMORY
from twitcher.wps_restapi.processes import processes


def make_request(**kw):
    request = DummyRequest(**kw)
    if request.registry.settings is None:
        request.registry.settings = {}
    request.registry.settings['twitcher.url'] = "localhost"
    request.registry.settings['twitcher.db_factory'] = DB_MEMORY
    return request


@mock.patch("twitcher.wps_restapi.processes.processes.wps_package.get_process_from_wps_request")
def test_deploy(mock_get_process):
    # given
    dummy_payload = {"processOffering": {
        "process": {
            "identifier": "workflow_stacker_sfs_id",
            "title": "Application StackCreation followed by SFS dynamically added by POST /processes",
            "owsContext": {
                "offering": {"code": "http://www.opengis.net/eoc/applicationContext/cwl",
                             "content": {"href": "http://some.host/applications/cwl/multisensor_ndvi.cwl"}}
            }
        }}}
    dummy_process_offering = {"package": "", "type": "", "inputs": "", "outputs": ""}
    dummy_process_offering.update(dummy_payload["processOffering"]["process"])
    mock_get_process.return_value = dummy_process_offering
    request = make_request(json=dummy_payload, method='POST')
    with mock.patch("twitcher.wps_restapi.processes.processes.ProcessDB") as process_class:
        # when
        response = processes.add_local_process(request)

        # then
        assert response.code == 200
        assert response.json["deploymentDone"]
        assert process_class.called
        process_info = process_class.call_args[0][0]
        assert "package" in process_info
        assert "payload" in process_info
        assert isinstance(process_info["payload"], dict)
