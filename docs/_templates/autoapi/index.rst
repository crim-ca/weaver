.. see original here: https://github.com/readthedocs/sphinx-autoapi/blob/master/autoapi/templates/index.rst

Source Code
=============

This page contains reference documentation of the source code.

.. toctree::
   :titlesonly:

   {% for page in pages|selectattr("is_top_level_object") %}
   {{ page.include_path }}
   {% endfor %}
