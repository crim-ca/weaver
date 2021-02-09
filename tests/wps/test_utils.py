import mock

from weaver.wps.utils import set_wps_language


def test_set_wps_language():
    wps = mock.Mock()
    languages = mock.Mock()
    wps.languages = languages
    languages.default = "en-US"
    languages.supported = ["en-US", "fr-CA"]

    set_wps_language(wps, "ru, fr;q=0.5")
    assert wps.language == "fr-CA"
