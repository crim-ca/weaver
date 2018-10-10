import lxml.etree
import requests
import urlparse

from typing import Iterable, Dict, Tuple
import logging

# todo: change this?
LOGGER = logging.getLogger("PACKAGE")


class OpenSearch(object):
    def __init__(self, osdd_url):
        """
        :param osdd_url: url for the OpenSearch Description Document
        """
        osdd_base, query = osdd_url.split("?", 1)
        self.osdd_url = osdd_base
        self.params = dict(urlparse.parse_qsl(query))

        self.params["httpAccept"] = "application/geo+json"

    def get_template_url(self):
        r = requests.get(self.osdd_url, params=self.params)
        r.raise_for_status()

        et = lxml.etree.fromstring(r.content)
        url = et.xpath("//*[local-name() = 'Url'][@rel='results']")[0]  # type: lxml.etree._Element
        return url.attrib["template"]

    def _prepare_query_url(self, template_url, params):
        # type: (str, Dict) -> Tuple[str, Dict]
        base_url, query = template_url.split("?", 1)

        query_params = {}
        template_parameters = urlparse.parse_qsl(query)

        allowed_names = set([p[0] for p in template_parameters])
        for key, value in template_parameters:
            if "{" in value and "}" in value:
                pass
            else:  # default value
                query_params[key] = value

        for key, value in params.items():
            if key not in allowed_names:
                # todo: raise twitcher-specific exception
                raise ValueError("{key} is not an allowed query parameter".format(key=key))
            query_params[key] = value

        return base_url, query_params

    def _query_features_paginated(self, params):
        start_page = 1
        template_url = self.get_template_url()
        base_url, query_params = self._prepare_query_url(template_url, params)
        while True:
            query_params["startPage"] = start_page
            response = requests.get(base_url, params=query_params)
            response.raise_for_status()
            json_body = response.json()
            for feature in json_body["features"]:
                yield feature, response.url
            total_results = json_body["totalResults"]
            items_per_page = json_body["itemsPerPage"]
            start_index = json_body["startIndex"]
            if start_index + items_per_page >= total_results:
                break
            start_page += 1

    def query_datasets(self, params=None):
        # type: (Dict) -> Iterable
        if params is None:
            params = {}

        for feature, url in self._query_features_paginated(params):
            try:
                data_links = [d["href"] for d in feature["properties"]["links"]["data"]]
            except KeyError:
                LOGGER.exception("Badly formatted json at: {}".format(url))
                raise

            file_link = [link for link in data_links if urlparse.urlparse(link).scheme == "file"]
            if not file_link:
                LOGGER.debug("No file:// download link for a feature at: {}".format(url))
            file_link = file_link[0]
            yield file_link

    def query_collections(self, params=None):
        # type: (Dict) -> Iterable
        if params is None:
            params = {}

        for feature, url in self._query_features_paginated(params):
            yield feature
