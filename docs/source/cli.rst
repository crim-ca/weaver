.. include:: references.rst
.. _cli:

******************
CLI
******************

Once `Weaver` package is installed (see :ref:`installation`), it provides a command line interface (:term:`CLI`)
as well as a :py:class:`weaver.cli.WeaverClient` to allow simplified interactions through shell calls or Python scripts.

This offers to the user methods to use file references (e.g.: local :term:`CWL` :term:`Application Package` definition)
to rapidly generate the corresponding :ref:`Deploy`, :term:`Describe`, :term:`Execute` requests and any other operation
described in :ref:`proc_operations` section.

Following are the detail of the :term:`CLI`.

.. https://sphinx-argparse.readthedocs.io/en/stable/usage.html
.. function must return an 'argparse.ArgumentParser' instance
.. argparse::
   :ref: weaver.cli.make_parser
   :prog: weaver
