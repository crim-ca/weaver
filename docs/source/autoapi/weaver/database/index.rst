:mod:`weaver.database`
======================

.. py:module:: weaver.database


Submodules
----------
.. toctree::
   :titlesonly:
   :maxdepth: 1

   base/index.rst
   mongodb/index.rst


Package Contents
----------------

.. data:: LOGGER
   

   

.. function:: get_db(container: AnySettingsContainer, reset_connection: bool = False) -> MongoDatabase

   Obtains the database connection from configured application settings.

   If :paramref:`reset_connection` is ``True``, the :paramref:`container` must be the application :class:`Registry` or
   any container that can retrieve it to accomplish reference reset. Otherwise, any settings container can be provided.


.. function:: includeme(config)


