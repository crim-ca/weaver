:mod:`weaver.wps_restapi.swagger_definitions`
=============================================

.. py:module:: weaver.wps_restapi.swagger_definitions

.. autoapi-nested-parse::

   This module should contain any and every definitions in use to build the swagger UI,
   so that one can update the swagger without touching any other files after the initial integration



Module Contents
---------------

.. data:: ViewInfo
   

   

.. py:class:: SchemaNode(*arg, **kw)



   Override the default :class:`colander.SchemaNode` to auto-handle ``default`` value substitution if an
   actual value was omitted during deserialization for a field defined with this schema and a ``default`` parameter.

   .. seealso::
       Implementation in :class:`SchemaNodeDefault`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: schema_type()
      :staticmethod:
      :abstractmethod:



.. py:class:: SequenceSchema(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: schema_type
      

      


.. py:class:: MappingSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: schema_type
      

      


.. py:class:: ExplicitMappingSchema(*arg, **kw)



   Original behaviour of :class:`colander.MappingSchema` implementation, where fields referencing
   to ``None`` values are kept as an explicit indication of an *undefined* or *missing* value for this field.

   Initialize self.  See help(type(self)) for accurate signature.


.. data:: API_TITLE
   :annotation: = Weaver REST API

   

.. data:: API_INFO
   

   

.. data:: URL
   :annotation: = url

   

.. data:: api_frontpage_uri
   :annotation: = /

   

.. data:: api_swagger_ui_uri
   :annotation: = /api

   

.. data:: api_swagger_json_uri
   :annotation: = /json

   

.. data:: api_versions_uri
   :annotation: = /versions

   

.. data:: api_conformance_uri
   :annotation: = /conformance

   

.. data:: processes_uri
   :annotation: = /processes

   

.. data:: process_uri
   :annotation: = /processes/{process_id}

   

.. data:: process_package_uri
   :annotation: = /processes/{process_id}/package

   

.. data:: process_payload_uri
   :annotation: = /processes/{process_id}/payload

   

.. data:: process_visibility_uri
   :annotation: = /processes/{process_id}/visibility

   

.. data:: process_jobs_uri
   :annotation: = /processes/{process_id}/jobs

   

.. data:: process_job_uri
   :annotation: = /processes/{process_id}/jobs/{job_id}

   

.. data:: process_quotes_uri
   :annotation: = /processes/{process_id}/quotations

   

.. data:: process_quote_uri
   :annotation: = /processes/{process_id}/quotations/{quote_id}

   

.. data:: process_results_uri
   :annotation: = /processes/{process_id}/jobs/{job_id}/result

   

.. data:: process_exceptions_uri
   :annotation: = /processes/{process_id}/jobs/{job_id}/exceptions

   

.. data:: process_logs_uri
   :annotation: = /processes/{process_id}/jobs/{job_id}/logs

   

.. data:: providers_uri
   :annotation: = /providers

   

.. data:: provider_uri
   :annotation: = /providers/{provider_id}

   

.. data:: provider_processes_uri
   :annotation: = /providers/{provider_id}/processes

   

.. data:: provider_process_uri
   :annotation: = /providers/{provider_id}/processes/{process_id}

   

.. data:: jobs_short_uri
   :annotation: = /jobs

   

.. data:: jobs_full_uri
   :annotation: = /providers/{provider_id}/processes/{process_id}/jobs

   

.. data:: job_full_uri
   :annotation: = /providers/{provider_id}/processes/{process_id}/jobs/{job_id}

   

.. data:: job_exceptions_uri
   :annotation: = /providers/{provider_id}/processes/{process_id}/jobs/{job_id}/exceptions

   

.. data:: job_short_uri
   :annotation: = /jobs/{job_id}

   

.. data:: quotes_uri
   :annotation: = /quotations

   

.. data:: quote_uri
   :annotation: = /quotations/{quote_id}

   

.. data:: bills_uri
   :annotation: = /bills

   

.. data:: bill_uri
   :annotation: = /bill/{bill_id}

   

.. data:: results_full_uri
   :annotation: = /providers/{provider_id}/processes/{process_id}/jobs/{job_id}/result

   

.. data:: results_short_uri
   :annotation: = /jobs/{job_id}/result

   

.. data:: result_full_uri
   :annotation: = /providers/{provider_id}/processes/{process_id}/jobs/{job_id}/result/{result_id}

   

.. data:: result_short_uri
   :annotation: = /jobs/{job_id}/result/{result_id}

   

.. data:: exceptions_full_uri
   :annotation: = /providers/{provider_id}/processes/{process_id}/jobs/{job_id}/exceptions

   

.. data:: exceptions_short_uri
   :annotation: = /jobs/{job_id}/exceptions

   

.. data:: logs_full_uri
   :annotation: = /providers/{provider_id}/processes/{process_id}/jobs/{job_id}/logs

   

.. data:: logs_short_uri
   :annotation: = /jobs/{job_id}/logs

   

.. data:: TAG_API
   :annotation: = API

   

.. data:: TAG_JOBS
   :annotation: = Jobs

   

.. data:: TAG_VISIBILITY
   :annotation: = Visibility

   

.. data:: TAG_BILL_QUOTE
   :annotation: = Billing & Quoting

   

.. data:: TAG_PROVIDERS
   :annotation: = Providers

   

.. data:: TAG_PROCESSES
   :annotation: = Processes

   

.. data:: TAG_GETCAPABILITIES
   :annotation: = GetCapabilities

   

.. data:: TAG_DESCRIBEPROCESS
   :annotation: = DescribeProcess

   

.. data:: TAG_EXECUTE
   :annotation: = Execute

   

.. data:: TAG_DISMISS
   :annotation: = Dismiss

   

.. data:: TAG_STATUS
   :annotation: = Status

   

.. data:: TAG_DEPLOY
   :annotation: = Deploy

   

.. data:: TAG_RESULTS
   :annotation: = Results

   

.. data:: TAG_EXCEPTIONS
   :annotation: = Exceptions

   

.. data:: TAG_LOGS
   :annotation: = Logs

   

.. data:: TAG_WPS
   :annotation: = WPS

   

.. data:: api_frontpage_service
   

   

.. data:: api_swagger_ui_service
   

   

.. data:: api_swagger_json_service
   

   

.. data:: api_versions_service
   

   

.. data:: api_conformance_service
   

   

.. data:: processes_service
   

   

.. data:: process_service
   

   

.. data:: process_package_service
   

   

.. data:: process_payload_service
   

   

.. data:: process_visibility_service
   

   

.. data:: process_jobs_service
   

   

.. data:: process_job_service
   

   

.. data:: process_quotes_service
   

   

.. data:: process_quote_service
   

   

.. data:: process_results_service
   

   

.. data:: process_exceptions_service
   

   

.. data:: process_logs_service
   

   

.. data:: providers_service
   

   

.. data:: provider_service
   

   

.. data:: provider_processes_service
   

   

.. data:: provider_process_service
   

   

.. data:: jobs_short_service
   

   

.. data:: jobs_full_service
   

   

.. data:: job_full_service
   

   

.. data:: job_short_service
   

   

.. data:: quotes_service
   

   

.. data:: quote_service
   

   

.. data:: bills_service
   

   

.. data:: bill_service
   

   

.. data:: results_full_service
   

   

.. data:: results_short_service
   

   

.. data:: exceptions_full_service
   

   

.. data:: exceptions_short_service
   

   

.. data:: logs_full_service
   

   

.. data:: logs_short_service
   

   

.. py:class:: ProcessPath(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: process_id
      

      


.. py:class:: ProviderPath(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: provider_id
      

      


.. py:class:: JobPath(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: job_id
      

      


.. py:class:: BillPath(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: bill_id
      

      


.. py:class:: QuotePath(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: quote_id
      

      


.. py:class:: ResultPath(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: result_id
      

      


.. py:class:: JsonHeader(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: content_type
      

      

   .. attribute:: name
      :annotation: = Content-Type

      


.. py:class:: HtmlHeader(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: content_type
      

      

   .. attribute:: name
      :annotation: = Content-Type

      


.. py:class:: XmlHeader(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: content_type
      

      

   .. attribute:: name
      :annotation: = Content-Type

      


.. py:class:: AcceptHeader(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: Accept
      

      


.. py:class:: AcceptLanguageHeader(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: AcceptLanguage
      

      

   .. attribute:: name
      :annotation: = Accept-Language

      


.. py:class:: KeywordList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: keyword
      

      


.. py:class:: JsonLink(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: href
      

      

   .. attribute:: rel
      

      

   .. attribute:: type
      

      

   .. attribute:: hreflang
      

      

   .. attribute:: title
      

      


.. py:class:: MetadataBase(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: title
      

      

   .. attribute:: role
      

      

   .. attribute:: type
      

      


.. py:class:: MetadataLink(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: MetadataValue(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: value
      

      

   .. attribute:: lang
      

      


.. py:class:: Metadata(*args, **kwargs)



   Allows specifying multiple supported mapping schemas variants for an underlying schema definition.
   Corresponds to the ``oneOf`` specifier of `OpenAPI` specification.

   Example::

       class Variant1(MappingSchema):
           [...fields of Variant1...]

       class Variant2(MappingSchema):
           [...fields of Variant2...]

       class RequiredByBoth(MappingSchema):
           [...fields required by both Variant1 and Variant2...]

       class LiteralDataDomainType(OneOfMappingSchema, RequiredByBoth):
           _one_of = (Variant1, Variant2)
           [...alternatively, field required by all variants here...]

   In the above example, the validation (ie: ``deserialize``) process will succeed if any of the ``_one_of``
   variants' validator completely succeed, and will fail if every variant fails validation execution.

   .. warning::
       Because the validation process requires only at least one of the variants to succeed, it is important to insert
       more *permissive* validators later in the ``_one_of`` iterator. For example, having a variant with all fields
       defined as optional (ie: with ``missing=drop``) inserted as first item in ``_one_of`` will make it always
       succeed regardless of following variants. This would have as side effect to never validate the other variants
       explicitly for specific field types and formats since the first option would always consist as a valid input
       fulfilling the specified definition (ie: an empty ``{}`` schema with all fields missing).

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: _one_of
      

      


.. py:class:: MetadataList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: item
      

      


.. py:class:: JsonLinkList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: item
      

      


.. py:class:: LandingPage(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: links
      

      


.. py:class:: Format(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: mimeType
      

      

   .. attribute:: schema
      

      

   .. attribute:: encoding
      

      


.. py:class:: FormatDescription(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: maximumMegabytes
      

      

   .. attribute:: default
      

      


.. py:class:: FormatDescriptionList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: format
      

      


.. py:class:: AdditionalParameterValuesList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: values
      

      


.. py:class:: AdditionalParameter(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: name
      

      

   .. attribute:: values
      

      


.. py:class:: AdditionalParameterList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: item
      

      


.. py:class:: AdditionalParameters(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: role
      

      

   .. attribute:: parameters
      

      


.. py:class:: AdditionalParametersList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: additionalParameter
      

      


.. py:class:: Content(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: href
      

      


.. py:class:: Offering(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: code
      

      

   .. attribute:: content
      

      


.. py:class:: OWSContext(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: offering
      

      


.. py:class:: DescriptionType(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: id
      

      

   .. attribute:: title
      

      

   .. attribute:: abstract
      

      

   .. attribute:: keywords
      

      

   .. attribute:: owsContext
      

      

   .. attribute:: metadata
      

      

   .. attribute:: additionalParameters
      

      

   .. attribute:: links
      

      


.. py:class:: MinMaxOccursInt(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: minOccurs
      

      

   .. attribute:: maxOccurs
      

      


.. py:class:: MinMaxOccursStr(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: minOccurs
      

      

   .. attribute:: maxOccurs
      

      


.. py:class:: WithMinMaxOccurs(*args, **kwargs)



   Allows specifying multiple supported mapping schemas variants for an underlying schema definition.
   Corresponds to the ``oneOf`` specifier of `OpenAPI` specification.

   Example::

       class Variant1(MappingSchema):
           [...fields of Variant1...]

       class Variant2(MappingSchema):
           [...fields of Variant2...]

       class RequiredByBoth(MappingSchema):
           [...fields required by both Variant1 and Variant2...]

       class LiteralDataDomainType(OneOfMappingSchema, RequiredByBoth):
           _one_of = (Variant1, Variant2)
           [...alternatively, field required by all variants here...]

   In the above example, the validation (ie: ``deserialize``) process will succeed if any of the ``_one_of``
   variants' validator completely succeed, and will fail if every variant fails validation execution.

   .. warning::
       Because the validation process requires only at least one of the variants to succeed, it is important to insert
       more *permissive* validators later in the ``_one_of`` iterator. For example, having a variant with all fields
       defined as optional (ie: with ``missing=drop``) inserted as first item in ``_one_of`` will make it always
       succeed regardless of following variants. This would have as side effect to never validate the other variants
       explicitly for specific field types and formats since the first option would always consist as a valid input
       fulfilling the specified definition (ie: an empty ``{}`` schema with all fields missing).

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: _one_of
      

      


.. py:class:: ComplexInputType(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: formats
      

      


.. py:class:: SupportedCrs(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: crs
      

      

   .. attribute:: default
      

      


.. py:class:: SupportedCrsList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: item
      

      


.. py:class:: BoundingBoxInputType(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: supportedCRS
      

      


.. py:class:: DataTypeSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: name
      

      

   .. attribute:: reference
      

      


.. py:class:: UomSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: AllowedValuesList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: allowedValues
      

      


.. py:class:: AllowedValues(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: allowedValues
      

      


.. py:class:: AllowedRange(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: minimumValue
      

      

   .. attribute:: maximumValue
      

      

   .. attribute:: spacing
      

      

   .. attribute:: rangeClosure
      

      


.. py:class:: AllowedRangesList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: allowedRanges
      

      


.. py:class:: AllowedRanges(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: allowedRanges
      

      


.. py:class:: AnyValue(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: anyValue
      

      


.. py:class:: ValuesReference(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: valueReference
      

      


.. py:class:: LiteralDataDomainType(*args, **kwargs)



   Allows specifying multiple supported mapping schemas variants for an underlying schema definition.
   Corresponds to the ``oneOf`` specifier of `OpenAPI` specification.

   Example::

       class Variant1(MappingSchema):
           [...fields of Variant1...]

       class Variant2(MappingSchema):
           [...fields of Variant2...]

       class RequiredByBoth(MappingSchema):
           [...fields required by both Variant1 and Variant2...]

       class LiteralDataDomainType(OneOfMappingSchema, RequiredByBoth):
           _one_of = (Variant1, Variant2)
           [...alternatively, field required by all variants here...]

   In the above example, the validation (ie: ``deserialize``) process will succeed if any of the ``_one_of``
   variants' validator completely succeed, and will fail if every variant fails validation execution.

   .. warning::
       Because the validation process requires only at least one of the variants to succeed, it is important to insert
       more *permissive* validators later in the ``_one_of`` iterator. For example, having a variant with all fields
       defined as optional (ie: with ``missing=drop``) inserted as first item in ``_one_of`` will make it always
       succeed regardless of following variants. This would have as side effect to never validate the other variants
       explicitly for specific field types and formats since the first option would always consist as a valid input
       fulfilling the specified definition (ie: an empty ``{}`` schema with all fields missing).

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: _one_of
      

      

   .. attribute:: defaultValue
      

      

   .. attribute:: dataType
      

      

   .. attribute:: uom
      

      


.. py:class:: LiteralDataDomainTypeList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: literalDataDomain
      

      


.. py:class:: LiteralInputType(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: literalDataDomains
      

      


.. py:class:: InputType(*args, **kwargs)



   Allows specifying multiple supported mapping schemas variants for an underlying schema definition.
   Corresponds to the ``oneOf`` specifier of `OpenAPI` specification.

   Example::

       class Variant1(MappingSchema):
           [...fields of Variant1...]

       class Variant2(MappingSchema):
           [...fields of Variant2...]

       class RequiredByBoth(MappingSchema):
           [...fields required by both Variant1 and Variant2...]

       class LiteralDataDomainType(OneOfMappingSchema, RequiredByBoth):
           _one_of = (Variant1, Variant2)
           [...alternatively, field required by all variants here...]

   In the above example, the validation (ie: ``deserialize``) process will succeed if any of the ``_one_of``
   variants' validator completely succeed, and will fail if every variant fails validation execution.

   .. warning::
       Because the validation process requires only at least one of the variants to succeed, it is important to insert
       more *permissive* validators later in the ``_one_of`` iterator. For example, having a variant with all fields
       defined as optional (ie: with ``missing=drop``) inserted as first item in ``_one_of`` will make it always
       succeed regardless of following variants. This would have as side effect to never validate the other variants
       explicitly for specific field types and formats since the first option would always consist as a valid input
       fulfilling the specified definition (ie: an empty ``{}`` schema with all fields missing).

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: _one_of
      

      


.. py:class:: InputTypeList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: input
      

      


.. py:class:: LiteralOutputType(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: literalDataDomains
      

      


.. py:class:: BoundingBoxOutputType(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: supportedCRS
      

      


.. py:class:: ComplexOutputType(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: formats
      

      


.. py:class:: OutputDataDescriptionType(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: OutputType(*args, **kwargs)



   Allows specifying multiple supported mapping schemas variants for an underlying schema definition.
   Corresponds to the ``oneOf`` specifier of `OpenAPI` specification.

   Example::

       class Variant1(MappingSchema):
           [...fields of Variant1...]

       class Variant2(MappingSchema):
           [...fields of Variant2...]

       class RequiredByBoth(MappingSchema):
           [...fields required by both Variant1 and Variant2...]

       class LiteralDataDomainType(OneOfMappingSchema, RequiredByBoth):
           _one_of = (Variant1, Variant2)
           [...alternatively, field required by all variants here...]

   In the above example, the validation (ie: ``deserialize``) process will succeed if any of the ``_one_of``
   variants' validator completely succeed, and will fail if every variant fails validation execution.

   .. warning::
       Because the validation process requires only at least one of the variants to succeed, it is important to insert
       more *permissive* validators later in the ``_one_of`` iterator. For example, having a variant with all fields
       defined as optional (ie: with ``missing=drop``) inserted as first item in ``_one_of`` will make it always
       succeed regardless of following variants. This would have as side effect to never validate the other variants
       explicitly for specific field types and formats since the first option would always consist as a valid input
       fulfilling the specified definition (ie: an empty ``{}`` schema with all fields missing).

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: _one_of
      

      


.. py:class:: OutputDescriptionList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: item
      

      


.. py:class:: JobExecuteModeEnum(*args, **kwargs)



   Override the default :class:`colander.SchemaNode` to auto-handle ``default`` value substitution if an
   actual value was omitted during deserialization for a field defined with this schema and a ``default`` parameter.

   .. seealso::
       Implementation in :class:`SchemaNodeDefault`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: schema_type
      

      


.. py:class:: JobControlOptionsEnum(*args, **kwargs)



   Override the default :class:`colander.SchemaNode` to auto-handle ``default`` value substitution if an
   actual value was omitted during deserialization for a field defined with this schema and a ``default`` parameter.

   .. seealso::
       Implementation in :class:`SchemaNodeDefault`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: schema_type
      

      


.. py:class:: JobResponseOptionsEnum(*args, **kwargs)



   Override the default :class:`colander.SchemaNode` to auto-handle ``default`` value substitution if an
   actual value was omitted during deserialization for a field defined with this schema and a ``default`` parameter.

   .. seealso::
       Implementation in :class:`SchemaNodeDefault`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: schema_type
      

      


.. py:class:: TransmissionModeEnum(*args, **kwargs)



   Override the default :class:`colander.SchemaNode` to auto-handle ``default`` value substitution if an
   actual value was omitted during deserialization for a field defined with this schema and a ``default`` parameter.

   .. seealso::
       Implementation in :class:`SchemaNodeDefault`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: schema_type
      

      


.. py:class:: JobStatusEnum(*args, **kwargs)



   Override the default :class:`colander.SchemaNode` to auto-handle ``default`` value substitution if an
   actual value was omitted during deserialization for a field defined with this schema and a ``default`` parameter.

   .. seealso::
       Implementation in :class:`SchemaNodeDefault`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: schema_type
      

      


.. py:class:: JobSortEnum(*args, **kwargs)



   Override the default :class:`colander.SchemaNode` to auto-handle ``default`` value substitution if an
   actual value was omitted during deserialization for a field defined with this schema and a ``default`` parameter.

   .. seealso::
       Implementation in :class:`SchemaNodeDefault`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: schema_type
      

      


.. py:class:: QuoteSortEnum(*args, **kwargs)



   Override the default :class:`colander.SchemaNode` to auto-handle ``default`` value substitution if an
   actual value was omitted during deserialization for a field defined with this schema and a ``default`` parameter.

   .. seealso::
       Implementation in :class:`SchemaNodeDefault`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: schema_type
      

      


.. py:class:: LaunchJobQuerystring(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: tags
      

      


.. py:class:: VisibilityValue(*arg, **kw)



   Override the default :class:`colander.SchemaNode` to auto-handle ``default`` value substitution if an
   actual value was omitted during deserialization for a field defined with this schema and a ``default`` parameter.

   .. seealso::
       Implementation in :class:`SchemaNodeDefault`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: schema_type
      

      

   .. attribute:: validator
      

      

   .. attribute:: example
      

      


.. py:class:: Visibility(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: value
      

      


.. py:class:: FrontpageEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: VersionsEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: ConformanceEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: SwaggerJSONEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: SwaggerUIEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: WPSParameters(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: service
      

      

   .. attribute:: request
      

      

   .. attribute:: version
      

      

   .. attribute:: identifier
      

      

   .. attribute:: data_inputs
      

      


.. py:class:: WPSBody(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: content
      

      


.. py:class:: WPSEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: querystring
      

      

   .. attribute:: body
      

      


.. py:class:: WPSXMLSuccessBodySchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: OkWPSResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = WPS operation successful

      

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: WPSXMLErrorBodySchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: ErrorWPSResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred on WPS endpoint.

      

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: ProviderEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: ProviderProcessEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: ProcessEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: ProcessPackageEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: ProcessPayloadEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: ProcessVisibilityGetEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: ProcessVisibilityPutEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: FullJobEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: ShortJobEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: ProcessResultsEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: FullResultsEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: ShortResultsEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: FullExceptionsEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: ShortExceptionsEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: ProcessExceptionsEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: FullLogsEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: ShortLogsEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: ProcessLogsEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: CreateProviderRequestBody(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: id
      

      

   .. attribute:: url
      

      

   .. attribute:: public
      

      


.. py:class:: InputDataType(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: id
      

      


.. py:class:: OutputDataType(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: id
      

      

   .. attribute:: format
      

      


.. py:class:: Output(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: transmissionMode
      

      


.. py:class:: OutputList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: output
      

      


.. py:class:: ProviderSummarySchema(*arg, **kw)



   WPS provider summary definition.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: id
      

      

   .. attribute:: url
      

      

   .. attribute:: title
      

      

   .. attribute:: abstract
      

      

   .. attribute:: public
      

      


.. py:class:: ProviderCapabilitiesSchema(*arg, **kw)



   WPS provider capabilities.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: id
      

      

   .. attribute:: url
      

      

   .. attribute:: title
      

      

   .. attribute:: abstract
      

      

   .. attribute:: contact
      

      

   .. attribute:: type
      

      


.. py:class:: TransmissionModeList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: item
      

      


.. py:class:: JobControlOptionsList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: item
      

      


.. py:class:: ExceptionReportType(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: code
      

      

   .. attribute:: description
      

      


.. py:class:: ProcessSummary(*arg, **kw)



   WPS process definition.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: version
      

      

   .. attribute:: jobControlOptions
      

      

   .. attribute:: outputTransmission
      

      

   .. attribute:: processDescriptionURL
      

      


.. py:class:: ProcessSummaryList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: item
      

      


.. py:class:: ProcessCollection(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: processes
      

      


.. py:class:: Process(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: inputs
      

      

   .. attribute:: outputs
      

      

   .. attribute:: visibility
      

      

   .. attribute:: executeEndpoint
      

      


.. py:class:: ProcessOutputDescriptionSchema(*arg, **kw)



   WPS process output definition.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: dataType
      

      

   .. attribute:: defaultValue
      

      

   .. attribute:: id
      

      

   .. attribute:: abstract
      

      

   .. attribute:: title
      

      


.. py:class:: JobStatusInfo(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: jobID
      

      

   .. attribute:: status
      

      

   .. attribute:: message
      

      

   .. attribute:: logs
      

      

   .. attribute:: result
      

      

   .. attribute:: exceptions
      

      

   .. attribute:: expirationDate
      

      

   .. attribute:: estimatedCompletion
      

      

   .. attribute:: duration
      

      

   .. attribute:: nextPoll
      

      

   .. attribute:: percentCompleted
      

      


.. py:class:: JobEntrySchema(*args, **kwargs)



   Allows specifying multiple supported mapping schemas variants for an underlying schema definition.
   Corresponds to the ``oneOf`` specifier of `OpenAPI` specification.

   Example::

       class Variant1(MappingSchema):
           [...fields of Variant1...]

       class Variant2(MappingSchema):
           [...fields of Variant2...]

       class RequiredByBoth(MappingSchema):
           [...fields required by both Variant1 and Variant2...]

       class LiteralDataDomainType(OneOfMappingSchema, RequiredByBoth):
           _one_of = (Variant1, Variant2)
           [...alternatively, field required by all variants here...]

   In the above example, the validation (ie: ``deserialize``) process will succeed if any of the ``_one_of``
   variants' validator completely succeed, and will fail if every variant fails validation execution.

   .. warning::
       Because the validation process requires only at least one of the variants to succeed, it is important to insert
       more *permissive* validators later in the ``_one_of`` iterator. For example, having a variant with all fields
       defined as optional (ie: with ``missing=drop``) inserted as first item in ``_one_of`` will make it always
       succeed regardless of following variants. This would have as side effect to never validate the other variants
       explicitly for specific field types and formats since the first option would always consist as a valid input
       fulfilling the specified definition (ie: an empty ``{}`` schema with all fields missing).

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: _one_of
      

      


.. py:class:: JobCollection(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: item
      

      


.. py:class:: CreatedJobStatusSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: status
      

      

   .. attribute:: location
      

      

   .. attribute:: jobID
      

      


.. py:class:: CreatedQuotedJobStatusSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: bill
      

      


.. py:class:: GetPagingJobsSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: jobs
      

      

   .. attribute:: limit
      

      

   .. attribute:: page
      

      


.. py:class:: GroupedJobsCategorySchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: category
      

      

   .. attribute:: jobs
      

      

   .. attribute:: count
      

      


.. py:class:: GroupedCategoryJobsSchema(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: job_group_category_item
      

      


.. py:class:: GetGroupedJobsSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: groups
      

      


.. py:class:: GetQueriedJobsSchema(*args, **kwargs)



   Allows specifying multiple supported mapping schemas variants for an underlying schema definition.
   Corresponds to the ``oneOf`` specifier of `OpenAPI` specification.

   Example::

       class Variant1(MappingSchema):
           [...fields of Variant1...]

       class Variant2(MappingSchema):
           [...fields of Variant2...]

       class RequiredByBoth(MappingSchema):
           [...fields required by both Variant1 and Variant2...]

       class LiteralDataDomainType(OneOfMappingSchema, RequiredByBoth):
           _one_of = (Variant1, Variant2)
           [...alternatively, field required by all variants here...]

   In the above example, the validation (ie: ``deserialize``) process will succeed if any of the ``_one_of``
   variants' validator completely succeed, and will fail if every variant fails validation execution.

   .. warning::
       Because the validation process requires only at least one of the variants to succeed, it is important to insert
       more *permissive* validators later in the ``_one_of`` iterator. For example, having a variant with all fields
       defined as optional (ie: with ``missing=drop``) inserted as first item in ``_one_of`` will make it always
       succeed regardless of following variants. This would have as side effect to never validate the other variants
       explicitly for specific field types and formats since the first option would always consist as a valid input
       fulfilling the specified definition (ie: an empty ``{}`` schema with all fields missing).

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: _one_of
      

      

   .. attribute:: total
      

      


.. py:class:: DismissedJobSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: status
      

      

   .. attribute:: jobID
      

      

   .. attribute:: message
      

      

   .. attribute:: percentCompleted
      

      


.. py:class:: QuoteProcessParametersSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: inputs
      

      

   .. attribute:: outputs
      

      

   .. attribute:: mode
      

      

   .. attribute:: response
      

      


.. py:class:: AlternateQuotation(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: id
      

      

   .. attribute:: title
      

      

   .. attribute:: description
      

      

   .. attribute:: price
      

      

   .. attribute:: currency
      

      

   .. attribute:: expire
      

      

   .. attribute:: created
      

      

   .. attribute:: details
      

      

   .. attribute:: estimatedTime
      

      


.. py:class:: AlternateQuotationList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: step
      

      


.. py:class:: Reference(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: href
      

      

   .. attribute:: mimeType
      

      

   .. attribute:: schema
      

      

   .. attribute:: encoding
      

      

   .. attribute:: body
      

      

   .. attribute:: bodyReference
      

      


.. py:class:: DataEncodingAttributes(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: mimeType
      

      

   .. attribute:: schema
      

      

   .. attribute:: encoding
      

      


.. py:class:: DataFloat(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: data
      

      


.. py:class:: DataInteger(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: data
      

      


.. py:class:: DataString(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: data
      

      


.. py:class:: DataBoolean(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: data
      

      


.. py:class:: ValueType(*args, **kwargs)



   Allows specifying multiple supported mapping schemas variants for an underlying schema definition.
   Corresponds to the ``oneOf`` specifier of `OpenAPI` specification.

   Example::

       class Variant1(MappingSchema):
           [...fields of Variant1...]

       class Variant2(MappingSchema):
           [...fields of Variant2...]

       class RequiredByBoth(MappingSchema):
           [...fields required by both Variant1 and Variant2...]

       class LiteralDataDomainType(OneOfMappingSchema, RequiredByBoth):
           _one_of = (Variant1, Variant2)
           [...alternatively, field required by all variants here...]

   In the above example, the validation (ie: ``deserialize``) process will succeed if any of the ``_one_of``
   variants' validator completely succeed, and will fail if every variant fails validation execution.

   .. warning::
       Because the validation process requires only at least one of the variants to succeed, it is important to insert
       more *permissive* validators later in the ``_one_of`` iterator. For example, having a variant with all fields
       defined as optional (ie: with ``missing=drop``) inserted as first item in ``_one_of`` will make it always
       succeed regardless of following variants. This would have as side effect to never validate the other variants
       explicitly for specific field types and formats since the first option would always consist as a valid input
       fulfilling the specified definition (ie: an empty ``{}`` schema with all fields missing).

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: _one_of
      

      


.. py:class:: Input(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: InputList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: item
      

      


.. py:class:: Execute(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: inputs
      

      

   .. attribute:: outputs
      

      

   .. attribute:: mode
      

      

   .. attribute:: notification_email
      

      

   .. attribute:: response
      

      


.. py:class:: Quotation(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: id
      

      

   .. attribute:: title
      

      

   .. attribute:: description
      

      

   .. attribute:: processId
      

      

   .. attribute:: price
      

      

   .. attribute:: currency
      

      

   .. attribute:: expire
      

      

   .. attribute:: created
      

      

   .. attribute:: userId
      

      

   .. attribute:: details
      

      

   .. attribute:: estimatedTime
      

      

   .. attribute:: processParameters
      

      

   .. attribute:: alternativeQuotations
      

      


.. py:class:: QuoteProcessListSchema(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: step
      

      


.. py:class:: QuoteSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: id
      

      

   .. attribute:: process
      

      

   .. attribute:: steps
      

      

   .. attribute:: total
      

      


.. py:class:: QuotationList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: item
      

      


.. py:class:: QuotationListSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: quotations
      

      


.. py:class:: BillSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: id
      

      

   .. attribute:: title
      

      

   .. attribute:: description
      

      

   .. attribute:: price
      

      

   .. attribute:: currency
      

      

   .. attribute:: created
      

      

   .. attribute:: userId
      

      

   .. attribute:: quotationId
      

      


.. py:class:: BillList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: item
      

      


.. py:class:: BillListSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: bills
      

      


.. py:class:: SupportedValues(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: DefaultValues(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: Unit(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: UnitType(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: unit
      

      


.. py:class:: ProcessInputDescriptionSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: minOccurs
      

      

   .. attribute:: maxOccurs
      

      

   .. attribute:: title
      

      

   .. attribute:: dataType
      

      

   .. attribute:: abstract
      

      

   .. attribute:: id
      

      

   .. attribute:: defaultValue
      

      

   .. attribute:: supportedValues
      

      


.. py:class:: ProcessDescriptionSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: outputs
      

      

   .. attribute:: inputs
      

      

   .. attribute:: description
      

      

   .. attribute:: id
      

      

   .. attribute:: label
      

      


.. py:class:: UndeploymentResult(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: id
      

      


.. py:class:: DeploymentResult(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: processSummary
      

      


.. py:class:: ProcessDescriptionBodySchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: process
      

      


.. py:class:: ProvidersSchema(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: providers_service
      

      


.. py:class:: JobOutputSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: id
      

      

   .. attribute:: data
      

      

   .. attribute:: href
      

      

   .. attribute:: mimeType
      

      

   .. attribute:: schema
      

      

   .. attribute:: encoding
      

      


.. py:class:: JobOutputsSchema(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: output
      

      


.. py:class:: OutputInfo(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: _one_of
      

      


.. py:class:: OutputInfoList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: output
      

      


.. py:class:: ExceptionTextList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: text
      

      


.. py:class:: ExceptionSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: Code
      

      

   .. attribute:: Locator
      

      

   .. attribute:: Text
      

      


.. py:class:: ExceptionsOutputSchema(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: exceptions
      

      


.. py:class:: LogsOutputSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: FrontpageParameterSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: name
      

      

   .. attribute:: enabled
      

      

   .. attribute:: url
      

      

   .. attribute:: doc
      

      


.. py:class:: FrontpageParameters(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: param
      

      


.. py:class:: FrontpageSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: message
      

      

   .. attribute:: configuration
      

      

   .. attribute:: parameters
      

      


.. py:class:: SwaggerJSONSpecSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: SwaggerUISpecSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: VersionsSpecSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: name
      

      

   .. attribute:: type
      

      

   .. attribute:: version
      

      


.. py:class:: VersionsList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: item
      

      


.. py:class:: VersionsSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: versions
      

      


.. py:class:: ConformanceList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: item
      

      


.. py:class:: ConformanceSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: conformsTo
      

      


.. py:class:: PackageBody(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: ExecutionUnit(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: _one_of
      

      


.. py:class:: ExecutionUnitList(*arg, **kw)



   Override the default :class:`colander.SequenceSchema` to auto-handle dropping missing entry definitions
   when its value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: item
      

      


.. py:class:: ProcessOffering(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: processVersion
      

      

   .. attribute:: process
      

      

   .. attribute:: processEndpointWPS1
      

      

   .. attribute:: jobControlOptions
      

      

   .. attribute:: outputTransmission
      

      


.. py:class:: ProcessDescriptionChoiceType(*args, **kwargs)



   Allows specifying multiple supported mapping schemas variants for an underlying schema definition.
   Corresponds to the ``oneOf`` specifier of `OpenAPI` specification.

   Example::

       class Variant1(MappingSchema):
           [...fields of Variant1...]

       class Variant2(MappingSchema):
           [...fields of Variant2...]

       class RequiredByBoth(MappingSchema):
           [...fields required by both Variant1 and Variant2...]

       class LiteralDataDomainType(OneOfMappingSchema, RequiredByBoth):
           _one_of = (Variant1, Variant2)
           [...alternatively, field required by all variants here...]

   In the above example, the validation (ie: ``deserialize``) process will succeed if any of the ``_one_of``
   variants' validator completely succeed, and will fail if every variant fails validation execution.

   .. warning::
       Because the validation process requires only at least one of the variants to succeed, it is important to insert
       more *permissive* validators later in the ``_one_of`` iterator. For example, having a variant with all fields
       defined as optional (ie: with ``missing=drop``) inserted as first item in ``_one_of`` will make it always
       succeed regardless of following variants. This would have as side effect to never validate the other variants
       explicitly for specific field types and formats since the first option would always consist as a valid input
       fulfilling the specified definition (ie: an empty ``{}`` schema with all fields missing).

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: _one_of
      

      


.. py:class:: Deploy(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: processDescription
      

      

   .. attribute:: immediateDeployment
      

      

   .. attribute:: executionUnit
      

      

   .. attribute:: deploymentProfileName
      

      

   .. attribute:: owsContext
      

      


.. py:class:: PostProcessesEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: PostProcessJobsEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: GetJobsQueries(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: detail
      

      

   .. attribute:: groups
      

      

   .. attribute:: page
      

      

   .. attribute:: limit
      

      

   .. attribute:: status
      

      

   .. attribute:: process
      

      

   .. attribute:: provider
      

      

   .. attribute:: sort
      

      

   .. attribute:: tags
      

      


.. py:class:: GetJobsRequest(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: querystring
      

      


.. py:class:: GetJobsEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: GetProcessJobsEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: GetProviderJobsEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: GetProcessJobEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: DeleteProcessJobEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: BillsEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: BillEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: ProcessQuotesEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: ProcessQuoteEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: GetQuotesQueries(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: page
      

      

   .. attribute:: limit
      

      

   .. attribute:: process
      

      

   .. attribute:: sort
      

      


.. py:class:: QuotesEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: querystring
      

      


.. py:class:: QuoteEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: PostProcessQuote(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: PostQuote(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: PostProcessQuoteRequestEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: GetProviders(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: PostProvider(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: GetProviderProcesses(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: GetProviderProcess(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      


.. py:class:: PostProviderProcessJobRequest(*arg, **kw)



   Launching a new process request definition.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: querystring
      

      

   .. attribute:: body
      

      


.. py:class:: OWSExceptionResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: code
      

      

   .. attribute:: locator
      

      

   .. attribute:: message
      

      


.. py:class:: ErrorJsonResponseBodySchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: code
      

      

   .. attribute:: status
      

      

   .. attribute:: title
      

      

   .. attribute:: description
      

      

   .. attribute:: exception
      

      


.. py:class:: UnauthorizedJsonResponseSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: ForbiddenJsonResponseSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: OkGetFrontpageResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: OkGetSwaggerJSONResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: OkGetSwaggerUIResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: OkGetVersionsResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: OkGetConformanceResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: OkGetProvidersListResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetProvidersListResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during providers listing.

      


.. py:class:: OkGetProviderCapabilitiesSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetProviderCapabilitiesResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during provider capabilities request.

      


.. py:class:: NoContentDeleteProviderSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorDeleteProviderResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during provider removal.

      


.. py:class:: NotImplementedDeleteProviderResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Provider removal not supported using referenced storage.

      


.. py:class:: OkGetProviderProcessesSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetProviderProcessesListResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during provider processes listing.

      


.. py:class:: GetProcessesQuery(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: providers
      

      

   .. attribute:: detail
      

      


.. py:class:: GetProcessesEndpoint(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: querystring
      

      


.. py:class:: OkGetProcessesListResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetProcessesListResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during processes listing.

      


.. py:class:: OkPostProcessDeployBodySchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: deploymentDone
      

      

   .. attribute:: processSummary
      

      

   .. attribute:: failureReason
      

      


.. py:class:: OkPostProcessesResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorPostProcessesResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during process deployment.

      


.. py:class:: OkGetProcessInfoResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: BadRequestGetProcessInfoResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Missing process identifier.

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetProcessResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during process description.

      


.. py:class:: OkGetProcessPackageSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetProcessPackageResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during process package description.

      


.. py:class:: OkGetProcessPayloadSchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetProcessPayloadResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during process payload description.

      


.. py:class:: ProcessVisibilityResponseBodySchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: value
      

      


.. py:class:: OkGetProcessVisibilitySchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetProcessVisibilityResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during process visibility retrieval.

      


.. py:class:: OkPutProcessVisibilitySchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorPutProcessVisibilityResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during process visibility update.

      


.. py:class:: OkDeleteProcessUndeployBodySchema(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: deploymentDone
      

      

   .. attribute:: identifier
      

      

   .. attribute:: failureReason
      

      


.. py:class:: OkDeleteProcessResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorDeleteProcessResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during process deletion.

      


.. py:class:: OkGetProviderProcessDescriptionResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetProviderProcessResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during provider process description.

      


.. py:class:: CreatedPostProvider(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorPostProviderResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during provider process registration.

      


.. py:class:: NotImplementedPostProviderResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Provider registration not supported using referenced storage.

      


.. py:class:: CreatedLaunchJobResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorPostProcessJobResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during process job submission.

      


.. py:class:: InternalServerErrorPostProviderProcessJobResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during process job submission.

      


.. py:class:: OkGetProcessJobResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: OkDeleteProcessJobResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: OkGetQueriedJobsResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetJobsResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during jobs listing.

      


.. py:class:: OkDismissJobResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorDeleteJobResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during job dismiss request.

      


.. py:class:: OkGetJobStatusResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetJobStatusResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during provider process description.

      


.. py:class:: Result(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: outputs
      

      

   .. attribute:: links
      

      


.. py:class:: OkGetJobResultsResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetJobResultsResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during job results listing.

      


.. py:class:: OkGetOutputResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetJobOutputResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during job results listing.

      


.. py:class:: CreatedQuoteExecuteResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorPostQuoteExecuteResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during quote job execution.

      


.. py:class:: CreatedQuoteRequestResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorPostQuoteRequestResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during quote submission.

      


.. py:class:: OkGetQuoteInfoResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetQuoteInfoResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during quote retrieval.

      


.. py:class:: OkGetQuoteListResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetQuoteListResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during quote listing.

      


.. py:class:: OkGetBillDetailResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetBillInfoResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during bill retrieval.

      


.. py:class:: OkGetBillListResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetBillListResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during bill listing.

      


.. py:class:: OkGetJobExceptionsResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetJobExceptionsResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during job exceptions listing.

      


.. py:class:: OkGetJobLogsResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: header
      

      

   .. attribute:: body
      

      


.. py:class:: InternalServerErrorGetJobLogsResponse(*arg, **kw)



   Override the default :class:`colander.MappingSchema` to auto-handle dropping missing field definitions
   when the corresponding value is either ``None``, :class:`colander.null` or :class:`colander.drop`.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: description
      :annotation: = Unhandled error occurred during job logs listing.

      


.. data:: get_api_frontpage_responses
   

   

.. data:: get_api_swagger_json_responses
   

   

.. data:: get_api_swagger_ui_responses
   

   

.. data:: get_api_versions_responses
   

   

.. data:: get_api_conformance_responses
   

   

.. data:: get_processes_responses
   

   

.. data:: post_processes_responses
   

   

.. data:: get_process_responses
   

   

.. data:: get_process_package_responses
   

   

.. data:: get_process_payload_responses
   

   

.. data:: get_process_visibility_responses
   

   

.. data:: put_process_visibility_responses
   

   

.. data:: delete_process_responses
   

   

.. data:: get_providers_list_responses
   

   

.. data:: get_provider_responses
   

   

.. data:: delete_provider_responses
   

   

.. data:: get_provider_processes_responses
   

   

.. data:: get_provider_process_responses
   

   

.. data:: post_provider_responses
   

   

.. data:: post_provider_process_job_responses
   

   

.. data:: post_process_jobs_responses
   

   

.. data:: get_all_jobs_responses
   

   

.. data:: get_single_job_status_responses
   

   

.. data:: delete_job_responses
   

   

.. data:: get_job_results_responses
   

   

.. data:: get_job_output_responses
   

   

.. data:: get_exceptions_responses
   

   

.. data:: get_logs_responses
   

   

.. data:: get_quote_list_responses
   

   

.. data:: get_quote_responses
   

   

.. data:: post_quotes_responses
   

   

.. data:: post_quote_responses
   

   

.. data:: get_bill_list_responses
   

   

.. data:: get_bill_responses
   

   

.. data:: wps_responses
   

   

.. function:: service_api_route_info(service_api: Service, settings: SettingsType) -> ViewInfo


