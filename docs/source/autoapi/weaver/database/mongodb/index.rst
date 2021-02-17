:mod:`weaver.database.mongodb`
==============================

.. py:module:: weaver.database.mongodb


Module Contents
---------------

.. data:: MongoDB
   :annotation: :Optional[Database]

   

.. data:: MongodbStores
   

   

.. data:: AnyMongodbStore
   

   

.. py:class:: MongoDatabase(: AnySettingsContainer, container)



   Return the unique identifier of db type matching settings.

   Initialize self.  See help(type(self)) for accurate signature.

   .. attribute:: _database
      

      

   .. attribute:: _settings
      

      

   .. attribute:: _stores
      

      

   .. attribute:: type
      :annotation: = mongodb

      

   .. method:: reset_store(self, store_type)


   .. method:: get_store(self: Union[str, Type[StoreInterface], AnyMongodbStoreType], store_type: Any, *store_args: Any, **store_kwargs) -> AnyMongodbStore

      Retrieve a store from the database.

      :param store_type: type of the store to retrieve/create.
      :param store_args: additional arguments to pass down to the store.
      :param store_kwargs: additional keyword arguments to pass down to the store.


   .. method:: get_session(self) -> Any


   .. method:: get_information(self) -> JSON

      :returns: {'version': version, 'type': db_type}


   .. method:: is_ready(self) -> bool


   .. method:: run_migration(self) -> None



.. function:: get_mongodb_connection(container: AnySettingsContainer) -> Database

   Obtains the basic database connection from settings.


.. function:: get_mongodb_engine(container: AnySettingsContainer) -> Database

   Obtains the database with configuration ready for usage.


