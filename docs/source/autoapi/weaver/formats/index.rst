:mod:`weaver.formats`
=====================

.. py:module:: weaver.formats


Module Contents
---------------

.. data:: CONTENT_TYPE_APP_CWL
   :annotation: = application/x-cwl

   

.. data:: CONTENT_TYPE_APP_FORM
   :annotation: = application/x-www-form-urlencoded

   

.. data:: CONTENT_TYPE_APP_NETCDF
   :annotation: = application/x-netcdf

   

.. data:: CONTENT_TYPE_APP_GZIP
   :annotation: = application/gzip

   

.. data:: CONTENT_TYPE_APP_HDF5
   :annotation: = application/x-hdf5

   

.. data:: CONTENT_TYPE_APP_TAR
   :annotation: = application/x-tar

   

.. data:: CONTENT_TYPE_APP_TAR_GZ
   :annotation: = application/tar+gzip

   

.. data:: CONTENT_TYPE_APP_YAML
   :annotation: = application/x-yaml

   

.. data:: CONTENT_TYPE_APP_ZIP
   :annotation: = application/zip

   

.. data:: CONTENT_TYPE_TEXT_HTML
   :annotation: = text/html

   

.. data:: CONTENT_TYPE_TEXT_PLAIN
   :annotation: = text/plain

   

.. data:: CONTENT_TYPE_APP_PDF
   :annotation: = application/pdf

   

.. data:: CONTENT_TYPE_APP_JSON
   :annotation: = application/json

   

.. data:: CONTENT_TYPE_APP_GEOJSON
   :annotation: = application/geo+json

   

.. data:: CONTENT_TYPE_APP_VDN_GEOJSON
   :annotation: = application/vnd.geo+json

   

.. data:: CONTENT_TYPE_APP_XML
   :annotation: = application/xml

   

.. data:: CONTENT_TYPE_IMAGE_GEOTIFF
   :annotation: = image/tiff; subtype=geotiff

   

.. data:: CONTENT_TYPE_TEXT_XML
   :annotation: = text/xml

   

.. data:: CONTENT_TYPE_ANY_XML
   

   

.. data:: CONTENT_TYPE_ANY
   :annotation: = */*

   

.. data:: _CONTENT_TYPE_EXTENSION_MAPPING
   :annotation: :Dict[str, str]

   

.. data:: _CONTENT_TYPE_FORMAT_MAPPING
   :annotation: :Dict[str, Format]

   

.. data:: _CONTENT_TYPE_SYNONYM_MAPPING
   

   

.. data:: IANA_NAMESPACE
   :annotation: = iana

   

.. data:: IANA_NAMESPACE_DEFINITION
   

   

.. data:: EDAM_NAMESPACE
   :annotation: = edam

   

.. data:: EDAM_NAMESPACE_DEFINITION
   

   

.. data:: EDAM_SCHEMA
   :annotation: = http://edamontology.org/EDAM_1.24.owl

   

.. data:: EDAM_MAPPING
   

   

.. data:: FORMAT_NAMESPACES
   

   

.. data:: WPS_VERSION_100
   :annotation: = 1.0.0

   

.. data:: WPS_VERSION_200
   :annotation: = 2.0.0

   

.. data:: OUTPUT_FORMAT_JSON
   :annotation: = json

   

.. data:: OUTPUT_FORMAT_XML
   :annotation: = xml

   

.. data:: OUTPUT_FORMATS
   

   

.. function:: get_format(mime_type: str) -> Format

   Obtains a :class:`Format` with predefined extension and encoding details from known MIME-types.


.. function:: get_extension(mime_type: str) -> str

   Retrieves the extension corresponding to :paramref:`mime_type` if explicitly defined, or by parsing it.


.. function:: get_cwl_file_format(mime_type: str, make_reference: bool = False, must_exist: bool = True, allow_synonym: bool = True) -> Union[Tuple[Optional[JSON], Optional[str]], Optional[str]]

   Obtains the corresponding `IANA`/`EDAM` ``format`` value to be applied under a `CWL` I/O ``File`` from
   the :paramref:`mime_type` (`Content-Type` header) using the first matched one.

   Lookup procedure is as follows:

   - If ``make_reference=False``:
       - If there is a match, returns ``tuple({<namespace-name: namespace-url>}, <format>)`` with:
           1) corresponding namespace mapping to be applied under ``$namespaces`` in the `CWL`.
           2) value of ``format`` adjusted according to the namespace to be applied to ``File`` in the `CWL`.
       - If there is no match but ``must_exist=False``, returns a literal and non-existing definition as
         ``tuple({"iana": <iana-url>}, <format>)``.
       - If there is no match but ``must_exist=True`` **AND** ``allow_synonym=True``, retry the call with the
         synonym if available, or move to next step. Skip this step if ``allow_synonym=False``.
       - Otherwise, returns ``(None, None)``

   - If ``make_reference=True``:
       - If there is a match, returns the explicit format reference as ``<namespace-url>/<format>``.
       - If there is no match but ``must_exist=False``, returns the literal reference as ``<iana-url>/<format>``
         (N.B.: literal non-official MIME-type reference will be returned even if an official synonym exists).
       - If there is no match but ``must_exist=True`` **AND** ``allow_synonym=True``, retry the call with the
         synonym if available, or move to next step. Skip this step if ``allow_synonym=False``.
       - Returns a single ``None`` as there is not match (directly or synonym).

   Note:
       In situations where ``must_exist=False`` is used and that the namespace and/or full format URL cannot be
       resolved to an existing reference, `CWL` will raise a validation error as it cannot confirm the ``format``.
       You must therefore make sure that the returned reference (or a synonym format) really exists when using
       ``must_exist=False`` before providing it to the `CWL` I/O definition. Setting ``must_exist=False`` should be
       used only for literal string comparison or pre-processing steps to evaluate formats.

   :param mime_type: Some reference, namespace'd or literal (possibly extended) MIME-type string.
   :param make_reference: Construct the full URL reference to the resolved MIME-type. Otherwise return tuple details.
   :param must_exist:
       Return result only if it can be resolved to an official MIME-type (or synonym if enabled), otherwise ``None``.
       Non-official MIME-type can be enforced if disabled, in which case `IANA` namespace/URL is used as it preserves
       the original ``<type>/<subtype>`` format.
   :param allow_synonym:
       Allow resolution of non-official MIME-type to an official MIME-type synonym if available.
       Types defined as *synonym* have semantically the same format validation/resolution for `CWL`.
       Requires ``must_exist=True``, otherwise the non-official MIME-type is employed directly as result.
   :returns: Resolved MIME-type format for `CWL` usage, accordingly to specified arguments (see description details).


.. function:: clean_mime_type_format(mime_type: str, suffix_subtype: bool = False, strip_parameters: bool = False) -> str

   Removes any additional namespace key or URL from :paramref:`mime_type` so that it corresponds to the generic
   representation (e.g.: ``application/json``) instead of the ``<namespace-name>:<format>`` mapping variant used
   in `CWL->inputs/outputs->File->format` or the complete URL reference.

   According to provided arguments, it also cleans up additional parameters or extracts sub-type suffixes.

   :param mime_type:
       MIME-type, full URL to MIME-type or namespace-formatted string that must be cleaned up.
   :param suffix_subtype:
       Remove additional sub-type specializations details separated by ``+`` symbol such that an explicit format like
       ``application/vnd.api+json`` returns only its most basic suffix format defined as``application/json``.
   :param strip_parameters:
       Removes additional MIME-type parameters such that only the leading part defining the ``type/subtype`` are
       returned. For example, this will get rid of ``; charset=UTF-8`` or ``; version=4.0`` parameters.

   .. note::
       Parameters :paramref:`suffix_subtype` and :paramref:`strip_parameters` are not necessarily exclusive.


