:mod:`weaver.processes.sources`
===============================

.. py:module:: weaver.processes.sources


Module Contents
---------------

.. data:: DATA_SOURCES
   

   Data sources configuration.

   Unless explicitly overridden, the configuration will be loaded from file as specified by``weaver.data_sources`` setting.
   Following JSON schema format is expected (corresponding YAML also supported):

   .. code-block:: json

     {
       "$schema": "http://json-schema.org/draft-07/schema#",
       "title": "Data Sources",
       "type": "object",
       "patternProperties": {
         ".*": {
           "type": "object",
           "required": [ "netloc", "ades" ],
           "additionalProperties": false,
           "properties": {
             "netloc": {
               "type": "string",
               "description": "Net location of a data source url use to match this data source."
             },
             "ades": {
               "type": "string",
               "description": "ADES endpoint where the processing of this data source can occur."
             },
             "default": {
               "type": "string",
               "description": "True indicate that if no data source match this one should be used (Use the first default)."
             }
           }
         }
       }
     }


.. function:: fetch_data_sources()


.. function:: get_default_data_source(data_sources)


.. function:: retrieve_data_source_url(data_source: Optional[Text]) -> Text

   Finds the data source URL using the provided data source identifier.

   :returns: found URL, 'default' data source if not found, or current weaver WPS Rest API base URL if `None`.


.. function:: get_data_source_from_url(data_url)


