:mod:`weaver.status`
====================

.. py:module:: weaver.status


Module Contents
---------------

.. data:: AnyStatusType
   

   

.. data:: STATUS_COMPLIANT_OGC
   :annotation: = STATUS_COMPLIANT_OGC

   

.. data:: STATUS_COMPLIANT_PYWPS
   :annotation: = STATUS_COMPLIANT_PYWPS

   

.. data:: STATUS_COMPLIANT_OWSLIB
   :annotation: = STATUS_COMPLIANT_OWSLIB

   

.. data:: STATUS_CATEGORY_FINISHED
   :annotation: = STATUS_CATEGORY_FINISHED

   

.. data:: STATUS_CATEGORY_RUNNING
   :annotation: = STATUS_CATEGORY_RUNNING

   

.. data:: STATUS_CATEGORY_FAILED
   :annotation: = STATUS_CATEGORY_FAILED

   

.. data:: STATUS_ACCEPTED
   :annotation: = accepted

   

.. data:: STATUS_STARTED
   :annotation: = started

   

.. data:: STATUS_PAUSED
   :annotation: = paused

   

.. data:: STATUS_SUCCEEDED
   :annotation: = succeeded

   

.. data:: STATUS_FAILED
   :annotation: = failed

   

.. data:: STATUS_RUNNING
   :annotation: = running

   

.. data:: STATUS_DISMISSED
   :annotation: = dismissed

   

.. data:: STATUS_EXCEPTION
   :annotation: = exception

   

.. data:: STATUS_UNKNOWN
   :annotation: = unknown

   

.. data:: JOB_STATUS_VALUES
   

   

.. data:: JOB_STATUS_CATEGORIES
   

   

.. data:: STATUS_PYWPS_MAP
   

   

.. data:: STATUS_PYWPS_IDS
   

   

.. function:: map_status(wps_status: AnyStatusType, compliant: str = STATUS_COMPLIANT_OGC) -> str

   Maps WPS statuses (weaver.status, OWSLib or PyWPS) to OWSLib/PyWPS compatible values.
   For each compliant combination, unsupported statuses are changed to corresponding ones (with closest logical match).
   Statuses are returned with `weaver.status.JOB_STATUS_VALUES` format (lowercase and not preceded by 'Process').

   :param wps_status: one of `weaver.status.JOB_STATUS_VALUES` to map to `compliant` standard or PyWPS `int` status.
   :param compliant: one of `STATUS_COMPLIANT_[...]` values.
   :returns: mapped status complying to the requested compliant category, or `STATUS_UNKNOWN` if no match found.


