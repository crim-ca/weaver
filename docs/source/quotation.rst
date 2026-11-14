.. include:: references.rst
.. _quotation:

******************************
Quotation and Billing
******************************

.. contents::
    :local:
    :depth: 3

Weaver implements the OGC API - Processes Quotation and Billing extensions to estimate the cost of a process before
execution and associate a bill with an execution made from a quote. Quotation endpoints are enabled by the
``weaver.quotation`` setting and are available only in supported deployment modes. See
:ref:`Configuration of Quotation Estimation <conf_quotation>` for enabling the feature and configuring the estimator.

.. seealso::
    - |ogc-proc-ext-quotation|_
    - |ogc-proc-ext-billing|_

.. _quote_estimation:
.. _quotation_quote_estimator:

Quote Estimation
================

An estimator is configured per process. It combines a flat rate and resource rates with either constant values or
estimators for values such as duration, memory, storage, CPU and GPU use. An estimator model can be supplied as an
ONNX model in the configuration, with process inputs mapped to model features. The resulting quote includes a total,
currency and optional cost breakdown.

The process must have a supported application package and estimator configuration. Estimator configuration can be
retrieved, replaced or reset at ``/processes/{process_id}/estimator``. A quote request submits the process parameters
to ``POST /processes/{process_id}/quotations``. Its response identifies the quote resource, which can be retrieved at
``/quotations/{quote_id}``. Quote estimation can complete synchronously or return an accepted response for later
retrieval, depending on the ``Prefer`` header and available execution time.

.. code-block:: shell

    curl -X POST "${WEAVER_URL}/processes/my-process/quotations" \
         -H "Content-Type: application/json" \
         -d '{"inputs": {"source": {"href": "https://example.org/input.nc"}}}'

.. _quotation_estimator_model:

Quote Estimator Model
---------------------

Each cost component can use a numeric constant or a model that predicts the component from selected process inputs.
For example, a constant ``duration_estimator`` is suitable when the expected duration does not depend on inputs, while
an ONNX model can estimate duration from input features such as file size. The estimator configuration maps process
input IDs to model input names or indices. A component's estimate is multiplied by its corresponding rate and added
to any flat rate to calculate the total.

The model must be in ONNX format and produce a single numeric estimate for the selected output. The schema provides
the supported estimator and mapping fields.

.. _quotation_estimator_config:

Quote Estimator Configuration
-----------------------------

The configuration contains a ``config`` object defining rates and estimators, and an ``inputs`` object describing
the process input features used for estimation. Optional ``outputs`` can assign weights to process outputs. Each
estimator may be a constant or an ONNX model with an optional mapping from model inputs to process input IDs.
Custom components are supported when their names end in ``_rate`` and ``_estimator``.

.. literalinclude:: ../../weaver/schemas/quotation/quote-estimator.yaml
    :caption: |quote-estimation-config|_ schema
    :language: yaml

.. _quotation_estimation_result:

Quote Estimation Result
-----------------------

The result contains a non-negative ``total`` and its currency. Additional fields provide the estimate, rate and
calculated cost for each component. The quote resource also reports its status and links.

.. literalinclude:: ../../weaver/schemas/quotation/quote-estimation-result.yaml
    :caption: |quote-estimation-result|_ schema
    :language: yaml

.. _quotation_billing:

Billing
==========

Executing a quote is a separate operation from estimating it. Submit ``POST /quotations/{quote_id}`` after the quote
has been marked as paid; an unpaid quote is rejected with HTTP 402. When execution is accepted, Weaver creates a bill
linked to the quote and resulting job and returns the bill and quote identifiers with the job response.

Use ``GET /bills`` to list bill identifiers and ``GET /bills/{bill_id}`` to retrieve a bill. Weaver records the
quotation and execution relationship, but these endpoints do not process payments.

.. _quotation_currency_conversion:

Currency Conversion
===================

The requested quote currency can be supplied with the ``X-Weaver-Currency`` header. If it is omitted, Weaver uses
``weaver.quotation_currency_default``. Currency conversion is optional: configure
``weaver.quotation_currency_converter`` and its corresponding token to use one of the supported exchange-rate
services: ``openexchangerates``, ``currencylayer``, ``exchangeratesapi``, ``fixer``, ``allratestoday``,
``scrapper`` or ``custom``. ``allratestoday`` does not require a token; ``custom`` also requires a converter URL.
See :ref:`Configuration of Quotation Estimation <conf_quotation>` for all related settings. If no converter is
configured or a conversion fails, the quote remains in the estimator's or configured default currency.

.. _quotation_api_examples:

API and Examples
================

The main operations are:

* ``GET``, ``PUT`` or ``DELETE /processes/{process_id}/estimator`` to inspect, set or reset a process estimator.
* ``POST /processes/{process_id}/quotations`` to request a quote, then ``GET /quotations/{quote_id}`` to inspect it.
* ``POST /quotations/{quote_id}`` to execute a paid quote.
* ``GET /quotations`` and ``GET /bills`` to list quotes and bills.
* ``GET /bills/{bill_id}`` to retrieve a bill.

For example, the following requests a quote, then retrieves its current status and estimate using the returned
``Location`` URL:

.. code-block:: shell

    curl -i -X POST "${WEAVER_URL}/processes/my-process/quotations" \
         -H "Content-Type: application/json" \
         -d '{"inputs": {"source": {"href": "https://example.org/input.nc"}}}'
    curl "${QUOTE_URL}"

Use the interactive API reference at ``${WEAVER_URL}/api`` for the complete request and response schemas, query
parameters and status details. Quote execution requires the quote to be paid before the ``POST`` request.
