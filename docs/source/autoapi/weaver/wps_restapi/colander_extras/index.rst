:mod:`weaver.wps_restapi.colander_extras`
=========================================

.. py:module:: weaver.wps_restapi.colander_extras


Module Contents
---------------

.. py:class:: DropableNoneSchema(*arg, **kw)



   Drops the underlying schema node if ``missing=drop`` was specified and that the value representing it is ``None``.

   Original behaviour of schema classes that can have children nodes such as :class:`colander.MappingSchema` and
   :class:`colander.SequenceSchema` are to drop the sub-node only if its value is resolved as :class:`colander.null`
   or :class:`colander.drop`. This results in "missing" definitions replaced by ``None`` in many implementations to
   raise :py:exc:`colander.Invalid` during deserialization. Inheriting this class in a schema definition
   will handle this situation automatically.

   Required schemas (without ``missing=drop``, i.e.: :class:`colander.required`) will still raise for undefined nodes.

   The following snippet shows the result that can be achieved using this schema class:

   .. code-block:: python

       class SchemaA(DropableNoneSchema, MappingSchema):
           field = SchemaNode(String())

       class SchemaB(MappingSchema):
           s1 = SchemaA(missing=drop)   # optional
           s2 = SchemaA()               # required

       SchemaB().deserialize({"s1": None, "s2": {"field": "ok"}})
       # >> {'s2': {'field': 'ok'}}

   .. seealso:
       https://github.com/Pylons/colander/issues/276
       https://github.com/Pylons/colander/issues/299

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: schema_type()
      :staticmethod:
      :abstractmethod:


   .. method:: deserialize(self, cstruct)

      Deserialize the :term:`cstruct` into an :term:`appstruct` based
      on the schema, run this :term:`appstruct` through the
      preparer, if one is present, then validate the
      prepared appstruct.  The ``cstruct`` value is deserialized into an
      ``appstruct`` unconditionally.

      If ``appstruct`` returned by type deserialization and
      preparation is the value :attr:`colander.null`, do something
      special before attempting validation:

      - If the ``missing`` attribute of this node has been set explicitly,
        return its value.  No validation of this value is performed; it is
        simply returned.

      - If the ``missing`` attribute of this node has not been set
        explicitly, raise a :exc:`colander.Invalid` exception error.

      If the appstruct is not ``colander.null`` and cannot be validated , a
      :exc:`colander.Invalid` exception will be raised.

      If a ``cstruct`` argument is not explicitly provided, it
      defaults to :attr:`colander.null`.



.. py:class:: VariableMappingSchema(unknown='ignore')



   Mapping schema that will allow **any** *unknown* field to remain present in the resulting deserialization.

   This definition is useful for defining a dictionary where some field names are not known in advance.
   Other fields that are explicitly specified with sub-schema nodes will be validated as per usual behaviour.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: SchemaNodeDefault(*arg, **kw)



   If ``default`` keyword is provided during :class:`colander.SchemaNode` creation, overrides the
   returned value by this default if missing from the structure during :func:`deserialize` call.

   Original behaviour was to drop the missing value instead of replacing by the default.
   Executes all other :class:`colander.SchemaNode` operations normally.

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: schema_type()
      :staticmethod:
      :abstractmethod:


   .. method:: deserialize(self, cstruct)

      Deserialize the :term:`cstruct` into an :term:`appstruct` based
      on the schema, run this :term:`appstruct` through the
      preparer, if one is present, then validate the
      prepared appstruct.  The ``cstruct`` value is deserialized into an
      ``appstruct`` unconditionally.

      If ``appstruct`` returned by type deserialization and
      preparation is the value :attr:`colander.null`, do something
      special before attempting validation:

      - If the ``missing`` attribute of this node has been set explicitly,
        return its value.  No validation of this value is performed; it is
        simply returned.

      - If the ``missing`` attribute of this node has not been set
        explicitly, raise a :exc:`colander.Invalid` exception error.

      If the appstruct is not ``colander.null`` and cannot be validated , a
      :exc:`colander.Invalid` exception will be raised.

      If a ``cstruct`` argument is not explicitly provided, it
      defaults to :attr:`colander.null`.



.. py:class:: OneOfCaseInsensitive(choices, msg_err=_MSG_ERR)



   Validator that ensures the given value matches one of the available choices, but allowing case insensitve values.

   Initialize self.  See help(type(self)) for accurate signature.


.. py:class:: OneOfMappingSchema(*args, **kwargs)



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

   .. method:: _one_of() -> Iterable[colander._SchemaMeta]
      :staticmethod:
      :abstractmethod:


   .. method:: deserialize_one_of(self, cstruct)


   .. method:: deserialize(self, cstruct)

      Deserialize the :term:`cstruct` into an :term:`appstruct` based
      on the schema, run this :term:`appstruct` through the
      preparer, if one is present, then validate the
      prepared appstruct.  The ``cstruct`` value is deserialized into an
      ``appstruct`` unconditionally.

      If ``appstruct`` returned by type deserialization and
      preparation is the value :attr:`colander.null`, do something
      special before attempting validation:

      - If the ``missing`` attribute of this node has been set explicitly,
        return its value.  No validation of this value is performed; it is
        simply returned.

      - If the ``missing`` attribute of this node has not been set
        explicitly, raise a :exc:`colander.Invalid` exception error.

      If the appstruct is not ``colander.null`` and cannot be validated , a
      :exc:`colander.Invalid` exception will be raised.

      If a ``cstruct`` argument is not explicitly provided, it
      defaults to :attr:`colander.null`.



.. py:class:: CustomTypeConversionDispatcher(custom_converters=None, default_converter=None)



   Initialize self.  See help(type(self)) for accurate signature.


.. function:: _dict_nested_equals(parent, child)

   Tests that a dict is 'contained' within a parent dict

   >>> parent = {"other": 2, "test": [{"inside": 1, "other_nested": 2}]}
   >>> child = {"test": [{"inside": 1}]}
   >>> _dict_nested_equals(parent, child)
   True

   :param dict parent: The dict that could contain the child
   :param dict child: The dict that could be nested inside the parent


