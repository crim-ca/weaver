Changes
*******

0.2.0
=====

- Fixes to handle invalid key characters ``"$"`` and ``"."`` during `CWL` package read/write operations to database
- Fixes some invalid `CWL` package generation from `WPS-1` references
- More cases handled for `WPS-1` to `CWL` ``WPS1Requirement`` conversion
  (``AllowedValues``, ``Default``, ``SupportedFormats``, ``minOccurs``, ``maxOccurs``)
- Add file format validation to generated `CWL` package from `WPS-1` `MIME-types`
- Allow auto-deployment of `WPS-REST` processes from `WPS-1` references specified by configuration
- Add many deployment and execution validation tests for ``WPS1Requirement``
- Add builtin application packages support for common operations

0.1.3
=====

- Add useful `Makefile` targets for deployment
- Add badges indications in ``README.rst`` for tracking from repo landing page
- Fix security issue of PyYAML requirement
- Fix some execution issues for ``Wps1Process``
- Fix some API schema erroneous definitions
- Additional logging of unhandled errors
- Improve some typing definitions

0.1.2
=====

- Introduce ``WPS1Requirement`` and corresponding ``Wps1Process`` to run a `WPS-1` process under `CWL`
- Remove `mongodb` requirement, assume it is running on an external service or docker image
- Add some typing definitions
- Fix some problematic imports
- Fix some PEP8 issues and PyCharm warnings

0.1.1
=====

- Modify `Dockerfile` to use lighter ``debian:latest`` instead of ``birdhouse/bird-base:latest``
- Modify `Dockerfile` to reduce build time by reusing built image layers (requirements installation mostly)
- Make some `buildout` dependencies optional to also reduce build time and image size
- Some additional striping of deprecated or invalid items from `Twitcher`_

0.1.0
=====

- Initial Release. Based off `Twitcher`_ tag `ogc-0.4.7`.

.. _Twitcher: https://github.com/Ouranosinc/Twitcher
