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
from weaver.utils import get_settings, request_extra, wait_secs

if TYPE_CHECKING:
    from typing import Union

    from celery.task import Task

    from weaver.datatype import Process, Quote
    from weaver.typedefs import QuoteEstimationParameters, QuoteProcessParameters

LOGGER = logging.getLogger(__name__)


def estimate_process_quote(quote, process):
    # type: (Quote, Process) -> QuoteEstimationParameters

    # TODO: replace by some fancy ml technique or something?
    settings = get_settings()
    price = random.uniform(0, 10)  # nosec
    currency = "CAD"
    seconds = int(random.uniform(5, 60) * 60 + random.uniform(5, 60))

    params = {"price": price, "currency": currency, "seconds": seconds}
    store = get_db(settings).get_store(StoreQuotes)
    quote = Quote(id=quote.id, status=QuoteStatus.COMPLETED, **params)
    store.update_quote(quote)
    return params


def estimate_workflow_quote(quote, process):
    # type: (Quote, Process) -> QuoteEstimationParameters
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
        process_quote_url = "{}/quotations".format(process_step_url)

        # FIXME: how to estimate data transfer if remote process (?)
        # FIXME: how to produce intermediate process inputs (?)
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
                body = resp.json()  # type: Union[QuoteEstimationParameters, QuoteProcessParameters]
                if body.get("status") == QuoteStatus.COMPLETED:
                    quote_steps.append(href)
                    quote_params.append(body)
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

    store = get_db(settings).get_store(StoreQuotes)
    quote = Quote(id=quote.id, status=QuoteStatus.COMPLETED, **params)
    store.update_quote(quote)
    return params


@app.task(bind=True)
def process_quote_estimator(task, quote, process):  # noqa: E811
    # type: (Task, str, str) -> QuoteEstimationParameters
    """
    Estimate :term:`Quote` parameters for the :term:`Process` execution.

    :param task: Celery Task that processes this quote.
    :param quote: Quote identifier associated to the requested estimation for the process execution.
    :param process: Process identifier for which to evaluate the execution quote.
    :return: Estimated quote parameters.
    """
    LOGGER.debug("Starting quote estimation [%s] for process [%s]", task.task_id, process)

    settings = get_settings()
    db = get_db(settings)
    p_store = db.get_store(StoreProcesses)
    q_store = db.get_store(StoreQuotes)
    process = p_store.fetch_by_id(process)  # type: Process
    quote = q_store.fetch_by_id(quote)  # type: Quote

    if process.type == ProcessType.WORKFLOW:
        params = estimate_workflow_quote(quote, process)
    else:
        params = estimate_process_quote(quote, process)
    return params
