:mod:`weaver.processes.opensearch`
==================================

.. py:module:: weaver.processes.opensearch


Module Contents
---------------

.. data:: LOGGER
   

   

.. function:: alter_payload_after_query(payload)

   When redeploying the package on ADES, strip out any EOImage parameter

   :param payload:


.. function:: validate_bbox(bbox)


.. function:: query_eo_images_from_wps_inputs(wps_inputs: Dict[str, Deque], eoimage_source_info: Dict[str, Dict], accept_mime_types: Dict[str, List[str]], settings: Optional[AnySettingsContainer] = None) -> Dict[str, Deque]

   Query OpenSearch using parameters in inputs and return file links.

   eoimage_ids is used to identify if a certain input is an eoimage.

   :param wps_inputs: inputs containing info to query
   :param eoimage_source_info: data source info of eoimages
   :param accept_mime_types: dict of list of accepted mime types, ordered by preference
   :param settings: application settings to retrieve request options as necessary.


.. function:: replace_with_opensearch_scheme(link)

   :param link: url to replace scheme


.. function:: load_wkt(wkt)

   :param wkt: to get the bounding box of
   :type wkt: string


.. py:class:: OpenSearchQuery(collection_identifier: str, osdd_url: str, catalog_search_field: str = 'parentIdentifier', settings: Optional[AnySettingsContainer] = None)



   :param collection_identifier: Collection ID to query
   :param osdd_url: Global OSDD url for opensearch queries.
   :param catalog_search_field: Name of the field for the collection identifier.
   :param settings: application settings to retrieve request options as necessary.

   .. attribute:: DEFAULT_MAX_QUERY_RESULTS
      :annotation: = 5

      

   .. method:: get_template_url(self)


   .. method:: _prepare_query_url(self: str, template_url: Dict, params) -> Tuple[str, Dict]

      :param template_url: url containing query parameters
      :param params: parameters to insert in formatted url


   .. method:: _fetch_datatsets_from_alternates_links(self, alternate_links)


   .. method:: _query_features_paginated(self: Dict, params) -> Iterable[Dict, str]

      :param params: query parameters


   .. method:: query_datasets(self: Dict, params: Tuple, accept_schemes: List, accept_mime_types) -> Iterable[str]

      Loop on every opensearch result feature and yield url matching required mime-type and scheme.
      Log a warning if a feature cannot yield a valid url (either no compatible mime-type or scheme)

      :param params: query parameters
      :param accept_schemes: only return links of this scheme
      :param accept_mime_types: list of accepted mime types, ordered by preference
      :raise KeyError: If the feature doesn't contain a json data section or an atom alternative link



.. function:: get_additional_parameters(input_data: Dict) -> List[Tuple[str, str]]

   :param input_data: Dict containing or not the "additionalParameters" key


.. py:class:: EOImageDescribeProcessHandler(: List[Dict], inputs)



   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: is_eoimage_input(input_data: Dict) -> bool
      :staticmethod:


   .. method:: get_allowed_collections(input_data: Dict) -> List
      :staticmethod:


   .. method:: make_aoi(id_)
      :staticmethod:


   .. method:: make_collection(identifier, allowed_values)
      :staticmethod:


   .. method:: make_toi(id_, start_date=True)
      :staticmethod:

      :param id_:
      :param start_date:  (Default value = True)


   .. method:: to_opensearch(self: bool, unique_aoi: bool, unique_toi) -> List[Dict]

      :param unique_aoi:
      :param unique_toi:



.. function:: get_eo_images_inputs_from_payload(payload)

   :param payload:


.. function:: get_original_collection_id(payload: Dict, wps_inputs: Dict[str, deque]) -> Dict[str, deque]

   When we deploy a Process that contains OpenSearch parameters, the collection identifier is modified.
   Ex: files -> collection
   Ex: s2 -> collection_s2, probav -> collection_probav
   This function changes the id in the execute request to the one in the deploy description.
   :param payload:
   :param wps_inputs:
   :return:


.. function:: get_eo_images_data_sources(payload: Dict, wps_inputs: Dict[str, deque]) -> Dict[str, Dict]

   :param payload: Deploy payload
   :param wps_inputs: Execute inputs


.. function:: get_eo_images_mime_types(payload: Dict) -> Dict[str, List]

   From the deploy payload, get the accepted mime types.
   :param payload: Deploy payload


.. function:: insert_max_occurs(payload: Dict, wps_inputs: Dict[str, Deque]) -> None

   Insert maxOccurs value in wps inputs using the deploy payload.
   :param payload: Deploy payload
   :param wps_inputs: WPS inputs


.. function:: modified_collection_identifiers(eo_image_identifiers)


.. function:: get_data_source(collection_id)


.. function:: get_eo_images_ids_from_payload(payload)


.. function:: replace_inputs_describe_process(inputs: List[Dict], payload: Dict) -> List[Dict]

   Replace ``EOImage`` inputs (if ``additionalParameter -> EOImage -> true``) with `OpenSearch` query parameters.


.. function:: _make_specific_identifier(param_name, identifier)

   Only adds an underscore between the parameters.


