import logging
import random
from datetime import timedelta
from typing import TYPE_CHECKING

from pyramid_celery import celery_app as app
from duration import to_iso8601

from weaver.database import get_db
from weaver.store.base import StoreProcesses
from weaver.utils import get_settings

if TYPE_CHECKING:
    from celery.task import Task

    from weaver.datatype import Process
    from weaver.typedefs import JobInputs, JobOutputs, TypedDict

    QuoteParameters = TypedDict("QuoteParameters", {
        "price": float,
        "currency": str,
        "estimatedTime": str
    })

LOGGER = logging.getLogger(__name__)


@app.task(bind=True)
def process_quote_estimator(task, process, inputs, outputs):  # noqa: E811
    # type: (Task, str, JobInputs, JobOutputs) -> QuoteParameters
    """
    Simulate quote parameters for the process execution.

    :param task: Celery Task that processes this quote.
    :param process: Process identifier for which to evaluate the execution quote.
    :param inputs: Submitted inputs of the expected execution to be quoted.
    :param outputs: Desired output of the expected execution to be quoted.
    :return: Estimated quote parameters.
    """
    LOGGER.debug("Starting quote estimation [%s] for process [%s]", task.task_id, process)

    settings = get_settings()
    store = get_db(settings).get_store(StoreProcesses)
    process = store.fetch_by_id(process)  # type: Process

    # TODO: replace by some fancy ml technique or something?
    # process.quote()
    price = random.uniform(0, 10)  # nosec
    currency = "CAD"
    estimated_time = to_iso8601(timedelta(minutes=random.uniform(5, 60)))  # nosec

    return {"price": price, "currency": currency, "estimatedTime": estimated_time}
