#!/usr/bin/env python
# -*- coding: utf-8 -*-

from typing import TYPE_CHECKING

from pywps.inout.storage import StorageAbstract

from weaver.wps.utils import get_wps_local_status_location

if TYPE_CHECKING:
    from weaver.typedefs import SettingsType


class ReferenceStatusLocationStorage(StorageAbstract):
    """
    Simple storage that simply redirects to a pre-existing status location.
    """
    # pylint: disable=W0222  # ignore mismatch signature of method params not employed

    def __init__(self, url_location, settings):
        # type: (str, SettingsType) -> None
        self._url = url_location
        # location might not exist yet based on worker execution timing
        self._file = get_wps_local_status_location(url_location, settings, must_exist=False)

    def url(self, *_, **__):
        """
        URL location of the XML status file.
        """
        return self._url

    def location(self, *_, **__):
        """
        Directory location of the XML status file.
        """
        return self._file

    def store(self, *_, **__):
        pass

    def write(self, *_, **__):
        pass
