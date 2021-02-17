:mod:`weaver.database.base`
===========================

.. py:module:: weaver.database.base


Module Contents
---------------

.. data:: StoreSelector
   

   

.. py:class:: DatabaseInterface(: AnySettingsContainer, _)

   Return the unique identifier of db type matching settings.

   Initialize self.  See help(type(self)) for accurate signature.

   .. method:: _get_store_type(store_type: StoreSelector) -> str
      :staticmethod:


   .. method:: get_store(self, store_type, *store_args, **store_kwargs)
      :abstractmethod:


   .. method:: reset_store(self: StoreSelector, store_type) -> None
      :abstractmethod:


   .. method:: get_session(self)
      :abstractmethod:


   .. method:: get_information(self) -> JSON
      :abstractmethod:

      :returns: {'version': version, 'type': db_type}


   .. method:: is_ready(self) -> bool
      :abstractmethod:


   .. method:: run_migration(self) -> None
      :abstractmethod:



