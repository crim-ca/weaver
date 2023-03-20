.. include:: references.rst
.. _quotation:

******************************
Quotation and Billing
******************************

.. contents::
    :local:
    :depth: 3


.. todo::
    - Summary description
    - Refer to |ogc-proc-ext-quotation|_ and |ogc-proc-ext-billing|_
    - Refer to :ref:`conf_quotation`

.. _quote_estimation:
.. _quotation_quote_estimator:

Quote Estimation
================

.. todo::
    - purpose/description
    - Detail |quote-estimator|

.. _quotation_estimator_model:

Quote Estimator Model
---------------------

.. todo::
    models vs constants, |ONNX-long|_ generalization

.. _quotation_estimator_config:

Quote Estimator Configuration
-----------------------------

.. todo::
    describe

.. literalinclude:: ../../weaver/schemas/quotation/quote-estimator.yaml
    :caption: |quote-estimation-config|_ schema
    :language: yaml

.. _quotation_estimation_result:

Quote Estimation Result
-----------------------

.. todo::
    describe

.. literalinclude:: ../../weaver/schemas/quotation/quote-estimation-result.yaml
    :caption: |quote-estimation-result|_ schema
    :language: yaml

.. _quotation_billing:

Billing
==========

.. todo::
    - Link between Quotation, Execution and Billing

.. _quotation_currency_conversion:

Currency Conversion
===================

.. todo::
    - Detail |currency-converter| (see ``weaver/quotation/estimation.py``)

.. _quotation_api_examples:

API and Examples
================

.. todo::
    - Detail API endpoints
    - Example requests
    - include design UML schemas (request/response state flow)
