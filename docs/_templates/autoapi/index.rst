.. see original here: https://github.com/readthedocs/sphinx-autoapi/blob/master/autoapi/templates/index.rst

Source Code
=============

This page contains reference documentation of the source code.

.. toctree::
   :titlesonly:

   {% for page in pages %}
   {% if page.top_level_object and page.display %}
   {{ page.include_path }}
   {% endif %}
   {% endfor %}
