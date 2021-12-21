.. include:: references.rst
.. _cli:

******************
CLI
******************

Once `Weaver` package is installed (see :ref:`installation`), it provides a command line interface (:term:`CLI`)
as well as a :py:class:`weaver.cli.WeaverClient` to allow simplified interactions through shell calls or Python scripts.

This offers to the user methods to use file references (e.g.: local :term:`CWL` :term:`Application Package` definition)
to rapidly operate with functionalities such as :ref:`Deploy <proc_op_deploy>`, :ref:`Describe <proc_op_describe>`,
:ref:`Execute <proc_op_execute>` and any other operation described in :ref:`proc_operations` section.

For details about using the Python :py:class:`weaver.cli.WeaverClient`, please refer directly to its documentation
and its underlying methods.

Following are the detail for the shell :term:`CLI` which provides the same features.

.. https://sphinx-argparse.readthedocs.io/en/stable/usage.html
.. function must return an 'argparse.ArgumentParser' instance
.. argparse::
    :module: weaver.cli
    :func: make_parser
    :prog: weaver
