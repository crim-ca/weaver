import logging
import random
import time
from typing import TYPE_CHECKING

from pyramid_celery import celery_app as app

from weaver.database import get_db
from weaver.exceptions import QuoteEstimationError
from weaver.processes.types import ProcessType
from weaver.processes.wps_package import get_package_workflow_steps, get_process_location
from weaver.quotation.status import QuoteStatus
from weaver.store.base import StoreProcesses, StoreQuotes
from weaver.utils import fully_qualified_name, get_settings, request_extra, wait_secs

if TYPE_CHECKING:
    from celery.app.task import Task

    from weaver.datatype import Process, Quote
    from weaver.quotation.status import AnyQuoteStatus
    from weaver.typedefs import AnyUUID

LOGGER = logging.getLogger(__name__)


def estimate_process_quote(quote, process):
    # type: (Quote, Process) -> Quote
    """
    Estimate execution price and time for an atomic :term:`Process` operation.

    Employs provided inputs and expected outputs and relevant metadata for the :term:`Process`.

    :param quote: Quote with references to process parameters.
    :param process: Targeted process for execution.
    :returns: Updated quote with estimates.
    """

    # TODO: replace by some fancy ml technique or something?
    quote.seconds = int(random.uniform(5, 60) * 60 + random.uniform(5, 60))  # nosec: B311
    quote.price = float(random.uniform(0, 100) * quote.seconds)              # nosec: B311
    quote.currency = "CAD"

    return quote


def estimate_workflow_quote(quote, process):
    # type: (Quote, Process) -> Quote
    """
    Loop :term:`Workflow` sub-:term:`Process` steps to get their respective :term:`Quote`.
    """
    settings = get_settings()
    process_url = process.href(settings)
    quote_steps = []
    quote_params = []
    workflow_steps = get_package_workflow_steps(process_url)
    for step in workflow_steps:
        # retrieve quote from provider ADES
        # TODO: data source mapping
        process_step_url = get_process_location(step["reference"])
        process_quote_url = f"{process_step_url}/quotations"

        # FIXME: how to estimate data transfer if remote process (?)
        # FIXME: how to produce intermediate process inputs (?) - remove xfail in functional test once resolved
        # FIXME: must consider fan-out in case of parallel steps
        data = {"inputs": [], "outputs": []}
        resp = request_extra("POST", process_quote_url, json=data, headers={"Prefer": "respond-async"})
        href = resp.headers.get("Location")
        status = QuoteStatus.SUBMITTED
        retry = 0
        abort = 3
        while status != QuoteStatus.COMPLETED and abort > 0:
            wait = wait_secs(retry)
            retry += 1
            resp = request_extra("GET", href)
            if resp.status_code != 200:
                abort -= 1
                wait = 5
            else:
                body = resp.json()
                status = QuoteStatus.get(body.get("status"))
                if status == QuoteStatus.COMPLETED:
                    quote_steps.append(href)
                    quote_params.append(body)
                    break
                if status == QuoteStatus.FAILED or status is None:
                    LOGGER.error("Quote estimation for sub-process [%s] under [%s] failed.", step["name"], process.id)
                    break
            if abort <= 0:
                time.sleep(wait)
    if len(workflow_steps) != len(quote_params):
        raise QuoteEstimationError("Could not obtain intermediate quote estimations for all Workflow steps.")

    # FIXME: what if different currencies are defined (?)
    currency = "CAD"
    params = {
        "price": 0,
        "currency": currency,
        "seconds": 0,
        "steps": quote_steps,
    }
    for step_params in quote_params:
        params["price"] += step_params["price"]
        params["seconds"] += step_params["estimatedSeconds"]

    quote.update(**params)
    return quote


@app.task(bind=True)
def process_quote_estimator(task, quote_id):
    # type: (Task, AnyUUID) -> AnyQuoteStatus
    """
    Estimate :term:`Quote` parameters for the :term:`Process` execution.

    :param task: Celery Task that processes this quote.
    :param quote_id: Quote identifier associated to the requested estimation for the process execution.
    :return: Estimated quote parameters.
    """
    task_id = task.request.id
    LOGGER.debug("Starting task [%s] for quote estimation [%s]", task_id, quote_id)

    settings = get_settings()
    db = get_db(settings)
    p_store = db.get_store(StoreProcesses)
    q_store = db.get_store(StoreQuotes)
    quote = q_store.fetch_by_id(quote_id)  # type: Quote
    process = p_store.fetch_by_id(quote.process)  # type: Process

    if quote.status != QuoteStatus.SUBMITTED:
        raise ValueError(f"Invalid quote [{quote.id}] ({quote.status}) cannot be processed.")

    quote.status = QuoteStatus.PROCESSING
    q_store.update_quote(quote)
    try:
        if process.type == ProcessType.WORKFLOW:
            quote = estimate_workflow_quote(quote, process)
        else:
            quote = estimate_process_quote(quote, process)

        quote.detail = "Quote processing complete."
        quote.status = QuoteStatus.COMPLETED
        LOGGER.info("Quote estimation complete [%s]. Task: [%s]", quote.id, task_id)
    except Exception as exc:
        LOGGER.error("Failed estimating quote [%s]. Task: [%s]", quote.id, task_id, exc_info=exc)
        quote.detail = f"Quote estimating failed. ERROR: ({fully_qualified_name(exc)} [{exc!s}]"
        quote.status = QuoteStatus.FAILED
    finally:
        q_store.update_quote(quote)

    LOGGER.debug("Finished task [%s] quote estimation [%s]", task_id, quote_id)
    return quote.status
