.. _examples:
.. include:: references.rst

********************************************
Process and Application Package Examples
********************************************

The principal source of examples can be found directly within |weaver-func-test-apps|_. Most :term:`Process` listed
in this repository employ an :term:`Application Package` defined using a locally provided :term:`CWL`. Some other
cases will refer to pre-deployed :term:`WPS` processes. Refer to corresponding |deploy-req-name|_ request payloads,
also provided in that location, that will indicate the kind of :term:`Process` definition employed through their
``executionUnit`` specification. Once successfully deployed on a :term:`ADES` or :term:`EMS`, the also provided
|exec-req-name|_ request body can be employed as format reference to run the operation (input values can be modified).

The general naming convention is:

    - ``DeployProcess_<PROCESS_ID>.json`` for the |deploy-req-name|_ request payload.
    - ``Execute_<PROCESS_ID>.json`` for the |exec-req-name|_ request payload.
    - ``<PROCESS_ID>.cwl`` for the :term:`CWL` :term:`Application Package` when applicable.

.. note::
    There can be minor variations (camel/snake case, upper/lower case) of the exact ``<PROCESS_ID>`` employed in the
    file names according to the different reference repositories.


Further examples are also available following `OGC Testbeds` developments. The produced applications in this case can
be found in |ogc-testbeds-apps|_. In that repository, the above naming convention will sometime be employed, but each
:term:`Process` is contained within its own sub-directory. Another naming conversion is sometime used, although the
files provide equivalent details:

    - ``<PROCESS_ID>/deploy.json`` for the |deploy-req-name|_ request payload.
    - ``<PROCESS_ID>/execute.json`` for the |exec-req-name|_ request payload.
    - ``<PROCESS_ID>/package.cwl`` for the :term:`CWL` :term:`Application Package` when applicable.
