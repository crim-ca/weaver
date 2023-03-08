import copy
import logging
import tempfile
import time

import requests
import yaml
from decimal import Decimal
from typing import TYPE_CHECKING

import colander
import simplejson
from beaker.cache import cache_region
from pyramid_celery import celery_app as app

from weaver.database import get_db
from weaver.exceptions import QuoteConversionError, QuoteEstimationError, QuoteException
from weaver.formats import ContentType, OutputFormat
from weaver.owsexceptions import OWSInvalidParameterValue
from weaver.processes.constants import JobInputsOutputsSchema
from weaver.processes.convert import convert_input_values_schema, convert_output_params_schema, normalize_ordered_io
from weaver.processes.types import ProcessType
from weaver.processes.wps_package import get_package_workflow_steps, get_process_location
from weaver.processes.utils import pull_docker
from weaver.quotation.status import QuoteStatus
from weaver.store.base import StoreProcesses, StoreQuotes
from weaver.utils import (
    fully_qualified_name,
    get_any_id,
    get_any_value,
    get_header,
    get_href_headers,
    get_settings,
    request_extra,
    wait_secs
)
from weaver.wps_restapi import swagger_definitions as sd

if TYPE_CHECKING:
    from typing import Dict, List, Optional, Union
    from typing_extensions import TypedDict

    from celery.app.task import Task
    from requests import Response

    from weaver.datatype import DockerAuthentication, Process, Quote
    from weaver.quotation.status import AnyQuoteStatus
    from weaver.utils import RequestCachingKeywords
    from weaver.typedefs import (
        AnyRequestMethod,
        AnyRequestType,
        AnySettingsContainer,
        AnyUUID,
        AnyValueType,
        Number,
        JSON,
        Price
    )

    EstimatorInputLiteral = TypedDict("EstimatorInputLiteral", {
        "value": Union[AnyValueType, List[AnyValueType]],
        "weight": Number,
    })
    EstimatorInputComplex = TypedDict("EstimatorInputComplex", {
        "size": Union[int, List[int]],
        "weight": Number,
    })
    EstimatorInputs = Dict[str, Union[EstimatorInputLiteral, EstimatorInputComplex]]


LOGGER = logging.getLogger(__name__)

# FIXME: define currency converter configs
# - https://docs.openexchangerates.org/reference/convert
# - https://currencylayer.com/documentation (see "Currency Conversion Endpoint" section)
# - https://exchangeratesapi.io/documentation/ (see "Convert Endpoint" section)
# - https://fixer.io/documentation (see "Convert Endpoint" section)
# - scrapper:
#   - https://www.thepythoncode.com/article/make-a-currency-converter-in-python
#   - https://www.x-rates.com/table/?from=CAD&amount=1
# - custom (by config)
CONVERTER_CONFIG = {

}


def get_quote_estimator_config(process):
    # type: (Process) -> JSON
    """
    Obtain the estimator from the process after validation.
    """
    try:
        estimator_config = validate_quote_estimator_config(process.estimator)
        if not estimator_config:
            raise QuoteEstimationError("Undefined configuration.")
        return estimator_config
    except (QuoteEstimationError, OWSInvalidParameterValue) as exc:
        LOGGER.warning(
            "Could not load quote estimator for process [%s]. Reverting to default.",
            process.id, exc_info=exc,
        )
    return {}


def validate_quote_estimator_config(estimator):
    # type: (JSON) -> JSON
    """
    Validate a quote estimator configuration against the expected schema.
    """
    try:
        estimator_config = sd.QuoteEstimatorSchema().deserialize(estimator)
    except colander.Invalid as exc:
        raise OWSInvalidParameterValue(json={
            "title": "InvalidParameterValue",
            "cause": f"Invalid schema: [{exc.msg!s}]",
            "error": exc.__class__.__name__,
            "value": exc.value
        })
    return estimator_config


def prepare_quote_estimator_config(quote, process):
    # type: (Quote, Process) -> JSON
    """
    Retrieves submitted quote input parameters and prepares them for the estimation using the process configuration.

    All submitted inputs are made available to the estimator(s).
    It is up to them to employ relevant inputs based on the quote estimation configuration applicable for this process.

    According to the ``quote-estimator`` schema, complex inputs must provide the file size, while literals provide the
    values directly. Weights are retrieved from the process configuration, but must be joined along inputs definition.

    .. seealso::
        https://github.com/crim-ca/weaver/blob/master/weaver/schemas/quote-estimator.yaml
    """
    process_input_types = {get_any_id(input_def): input_def["type"] for input_def in process.inputs}
    quotation_inputs = convert_input_values_schema(quote.parameters.get("inputs", {}), JobInputsOutputsSchema.OGC)
    estimator_config = copy.deepcopy(process.estimator)
    estimator_inputs = estimator_config.get("inputs", {})  # type: EstimatorInputs
    # Estimators are allowed to use different IDs than the process IDs, as long as they define a relevant mapping.
    # Avoid checking all estimator mappings, simply provide all inputs, and let them pick-and-choose what they need.
    for input_id, input_param in quotation_inputs.items():
        input_key = get_any_value(input_param, key=True)
        input_val = input_param[input_key]
        estimator_inputs.setdefault(input_id, {})  # type: ignore
        estimator_inputs[input_id].setdefault("weight", 1.0)
        input_type = process_input_types[input_id]
        if input_type == "literal" and input_key in ["data", "value"]:
            estimator_inputs[input_id]["value"] = input_val
        elif input_type == "complex" and input_key == "href":
            input_array = isinstance(input_val, list)
            input_info = [
                get_href_headers(
                    href,
                    download_headers=False,
                    location_headers=False,
                    content_headers=True,
                )
                for href in (input_val if input_array else [input_val])
            ]
            input_size = [
                get_header("Content-Length", info, default=0)
                for info in input_info
            ]
            estimator_inputs[input_id]["size"] = input_size if input_array else input_size[0]
        else:  # pragma: no cover
            raise NotImplementedError(
                "Quote estimator input combination not supported: "
                f"(type: {input_type}, key: {input_key}, id: {input_id})"
            )

    # FIXME: handle quotation outputs (?)
    #   Quotation output are only pseudo-definitions for chaining applications in a Workflow
    #   (i.e.: for providing the next process's quotation inputs).
    #   There is no way to do this at the moment, as submitted execution/quotation outputs are "requested" outputs
    #   (transmission mode, format, etc.) and not "expected" outputs (value/href).
    # process_output_types = {get_any_id(i_def): i_def["type"] for i_def in process.outputs}
    # quotation_outputs = convert_output_params_schema(quote.parameters.get("outputs", {}), JobInputsOutputsSchema.OGC)

    LOGGER.debug("Resolved Estimator inputs for Quote [%s] of Process [%s]:\n%s", OutputFormat.)
    return estimator_config


def get_currency(request=None):
    # type: (Optional[AnyRequestType]) -> str
    settings = get_settings(request)
    currency = get_header("X-Weaver-Currency", request.headers)
    currency = sd.PriceCurrency(missing=None).get("currency").deserialize(currency)
    currency = currency or settings.get("weaver.quotation_currency_default") or "USD"
    return currency


@cache_region("quotation")
def request_convert_cost(method, url, kwargs):
    # type: (AnyRequestMethod, str, RequestCachingKeywords) -> Response
    return requests.request(method, url, **kwargs)


def convert_exchange_rate(amount, convert_currency):
    # type: (Decimal, str) -> Price
    """
    Convert the cost value using the requested currency.
    """
    default_currency = get_currency()
    if not convert_currency:
        return {"amount": amount, "currency": default_currency}

    settings = get_settings()
    converter_type = settings.get("weaver.quotation_currency_converter")
    if converter_type not in CONVERTER_CONFIG:
        LOGGER.warning("No converter specified in settings to obtain quote amount in requested currency.")
        return {"amount": amount, "currency": default_currency}

    try:
        converter = CONVERTER_CONFIG[converter_type]
        headers = {"Accept": ContentType.APP_JSON}
        args = {"amount": str(amount), "to": convert_currency, "from": default_currency}
        resp = request_extra("GET", converter["url"], cache_request=request_convert_cost, params=args, headers=headers)
        if not resp.status_code == 200:
            raise QuoteConversionError("Bad quote currency response from [%s].", converter["url"])
        data = simplejson.loads(resp.text, use_decimal=True)
        result = converter["parser"](data)
        return {"amount": result, "currency": convert_currency}
    except Exception as exc:
        LOGGER.warning("Failed quote currency conversion. Using default [%s].", default_currency, exc_info=exc)
    return {"amount": amount, "currency": default_currency}


def estimate_process_quote(quote, process, settings=None):
    # type: (Quote, Process, Optional[AnySettingsContainer]) -> Quote
    """
    Estimate execution price and time for an atomic :term:`Process` operation.

    Employs provided inputs and expected outputs and relevant metadata for the :term:`Process`.

    :param quote: Quote with references to process parameters.
    :param process: Targeted process for execution.
    :param settings: Application settings.
    :returns: Updated quote with estimates.
    """
    settings = get_settings(settings)
    quote_docker_img = settings.get("weaver.quotation_docker_image")
    quote_docker_usr = settings.get("weaver.quotation_docker_username")  # usr/pwd can be empty if image public
    quote_docker_pwd = settings.get("weaver.quotation_docker_password")
    if not quote_docker_img:
        raise QuoteEstimationError("Missing quote estimator Docker image reference from settings.")

    auth_params = {}
    if quote_docker_usr and quote_docker_pwd:
        auth_params = {"auth_username": quote_docker_usr, "auth_password": quote_docker_pwd}
    docker_ref = DockerAuthentication("Basic", auth_link=quote_docker_img, **auth_params)
    docker_client = pull_docker(docker_ref)
    if not docker_client:
        raise QuoteEstimationError("Unable to retrieve quote estimator Docker image reference from settings.")

    try:
        quote_config = prepare_quote_estimator_config(quote, process)
        with tempfile.NamedTemporaryFile(suffix=".yaml", encoding="utf-8") as quote_file:
            yaml.safe_dump(quote_config, quote_file, indent=2, sort_keys=False, encoding="utf-8", allow_unicode=True)
            out_quote_json = docker_client.containers.run(
                docker_ref.image,
                ["--json", "--detail", "--config", "/tmp/quote-config.yaml"],
                volumes={quote_file.name: {"bind": "/tmp/quote-config.yaml", "mode": "ro"}},
                auto_remove=True,
                remove=True,
            )
        quote.results = simplejson.loads(out_quote_json, use_decimal=True)
        quote.price = convert_exchange_rate(quote.amount, quote.currency)
        quote.seconds = int(quote.results.get("duration", {}).get("estimate", 0))
        quote.process = process
    except QuoteException:
        raise
    except Exception as exc:
        err = "Docker execution failed to retrieve quote estimation."
        LOGGER.error(err, exc_info=exc)
        raise QuoteEstimationError(err) from exc
    return quote


def estimate_workflow_quote(quote, process, settings=None):
    # type: (Quote, Process, Optional[AnySettingsContainer]) -> Quote
    """
    Loop :term:`Workflow` sub-:term:`Process` steps to get their respective :term:`Quote`.
    """
    settings = get_settings(settings)
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
    currency = "USD"
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
def execute_quote_estimator(task, quote_id):
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
            quote = estimate_workflow_quote(quote, process, settings=settings)
        else:
            quote = estimate_process_quote(quote, process, settings=settings)
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
