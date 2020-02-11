Changes
*******

Unreleased
==========

Changes:
-------------

- Simplify docker image generation and make base/manager/worker variants all available under the same docker
  repo `docker-registry.crim.ca/ogc/weaver <docker-registry.crim.ca/ogc/weaver>`_  with different tags.
- Add *planned future support* of ``Accept-Language`` header for `WPS-1/2` (``geopython/OWSLib 0.20.0``) (#74).

Fixes:
-------------

- Fix `readthedocs <https://img.shields.io/readthedocs/pavics-weaver>`_ documentation generation.
- Fix ``.travis`` docker image build condition.
- Fix ``geopython/OWSLib>=0.19.1`` requirement for Python 3.8 support (#62).

1.0.0 (2020-01-28)
==================

New Features:
-------------

- Add ``notification_email`` field to ``Job`` datatype that stores an encrypted email (according to settings) when
  provided in the job submission body (#44).
- Add ability to filter jobs with ``notification_email`` query parameter (#44).
- Add jobs statistics grouping by specific fields using comma-separated list ``groups`` query parameter (#46).
- Add some tests to evaluate new job search methods / grouping results and responses (#44, #46).
- Add handling of multiple `CWL` field ``format`` for ``File`` type.
- Add missing ontology reference support for `CWL` field ``format`` by defaulting to `IANA` namespace.
- Add support for I/O ``array`` of ``enum`` (ie: multiple values of ``AllowedValues`` for a given input) (#30).
- Add support of ``label`` synonym as ``title`` for inputs and process description
  (`CWL` specifying a ``label`` will set it in `WPS` process) (#31)
- Add support of input ``minOccurs`` and ``maxOccurs`` as ``int`` while maintaining ``str`` support (#14).
- Add conformance route with implementation links (#53).
- Add additional landing page link details (#54).
- Add ``weaver.wps_restapi.colander_extras.DropableNoneSchema`` to auto-handle some schema JSON deserialization.
- Add ``weaver.wps_restapi.colander_extras.VariableMappingSchema`` to auto-handle some schema JSON deserialization.
- Add more functional tests (#11, #17).

Changes:
-------------

- Use ``bump2version`` and move all config under ``setup.cfg``.
- Remove enforced ``text/plain`` for `CWL` ``File`` when missing ``format`` field.
- Replace bubbling up of too verbose unhandled exceptions (500 Internal Server Error) by summary message and additional
  internal logging for debugging the cause using an utility exception log decorator.
- Use the same exception log decorator to simplify function definitions when HTTP exceptions are already handled.
- Make ``null`` reference a singleton so that multiple instantiation calls all refer to the same instance and produce
  the expected behaviour of ``<x> is null`` instead of hard-to-identify errors because of english syntax.
- Remove unused function ``weaver.utils.replace_caps_url`` and corresponding tests.
- Remove ``weaver.processes.utils.jsonify_value`` duplicated by ``weaver.processes.wps_package.complex2json``.
- Use more JSON body schema validation using API schema definitions deserialization defined by ``weaver.datatype``.
- Enforce ``builtin`` processes registration on startup to receive applicable updates.
- Provide 2 separate docker images for `Weaver` *manager* and *worker*, corresponding to the `EMS/ADES` API and the
  ``celery`` job runner respectively.
- Update Apache license.

Fixes:
-------------

- Adjust some typing definitions incorrectly specified.
- Fix some failing functionality tests (#11, #17).
- Fix I/O field ordering preserved as specified in payload or loaded reference file.
- Fix setting ``minOccurs=0`` when a ``default`` is specified in the corresponding `CWL` I/O (#17, #25).
- Fix incorrectly overridden ``maxOccurs="unbounded"`` by ``maxOccurs="1"`` when a partial array input definition
  is specified without explicit ``maxOccurs`` in `WPS` payload (#17, #25).
- Fix case where omitted ``format[s]`` in both `CWL` and `WPS` deploy bodies generated a process description with
  complex I/O (file) without required ``formats`` field. Default ``text/plain`` format is now automatically added.
- Fix case where ``format[s]`` lists between `CWL` and `WPS` where incorrectly merged.
- Fix ``metadata`` field within a WPS I/O incorrectly parsed when provided by a WPS-1/2 `XML` process definition.
- Fix invalid JSON response formatting on failing schema validation of process deployment body.
- Fix docker images to support ``pserve`` when using ``gunicorn>=20.x`` dropping support of ``--paste`` config feature.
- Fix multiple Python 2/3 compatibility issues.

0.2.2 (2019-05-31)
==================

- Support notification email subject template.

0.2.1 (2019-05-29)
==================

- Add per-process email notification template.

0.2.0 (2019-03-26)
==================

- Fixes to handle invalid key characters ``"$"`` and ``"."`` during `CWL` package read/write operations to database.
- Fixes some invalid `CWL` package generation from `WPS-1` references.
- More cases handled for `WPS-1` to `CWL` ``WPS1Requirement`` conversion
  (``AllowedValues``, ``Default``, ``SupportedFormats``, ``minOccurs``, ``maxOccurs``).
- Add file format validation to generated `CWL` package from `WPS-1` `MIME-types`.
- Allow auto-deployment of `WPS-REST` processes from `WPS-1` references specified by configuration.
- Add many deployment and execution validation tests for ``WPS1Requirement``.
- Add ``builtin`` application packages support for common operations.

0.1.3
=====

- Add useful `Makefile` targets for deployment.
- Add badges indications in ``README.rst`` for tracking from repo landing page.
- Fix security issue of PyYAML requirement.
- Fix some execution issues for ``Wps1Process``.
- Fix some API schema erroneous definitions.
- Additional logging of unhandled errors.
- Improve some typing definitions.

0.1.2
=====

- Introduce ``WPS1Requirement`` and corresponding ``Wps1Process`` to run a `WPS-1` process under `CWL`.
- Remove `mongodb` requirement, assume it is running on an external service or docker image.
- Add some typing definitions.
- Fix some problematic imports.
- Fix some PEP8 issues and PyCharm warnings.

0.1.1
=====

- Modify `Dockerfile` to use lighter ``debian:latest`` instead of ``birdhouse/bird-base:latest``.
- Modify `Dockerfile` to reduce build time by reusing built image layers (requirements installation mostly).
- Make some `buildout` dependencies optional to also reduce build time and image size.
- Some additional striping of deprecated or invalid items from `Twitcher`_.

0.1.0
=====

- Initial Release. Based off `Twitcher`_ tag `ogc-0.4.7`.

.. _Twitcher: https://github.com/Ouranosinc/Twitcher
