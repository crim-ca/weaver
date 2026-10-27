"""
Definitions related to :term:`Provenance` features and the :term:`W3C` ``PROV`` specification.
"""
import datetime
import hashlib
import json
from typing import TYPE_CHECKING, NamedTuple, cast
from urllib.parse import urlparse

from cwltool.cwlprov import provenance_constants as cwl_prov_const
from cwltool.cwlprov.ro import ResearchObject
from prov import constants as prov_const
from prov.identifier import Identifier, QualifiedName
from prov.model import ProvDocument, ProvRelation

from weaver.__meta__ import __version__ as weaver_version
from weaver.base import Constants
from weaver.formats import ContentType, OutputFormat
from weaver.utils import get_weaver_url

if TYPE_CHECKING:
    from typing import Any, List, Optional, Tuple, Union
    from uuid import UUID

    from cwltool.cwlprov.provenance_profile import ProvenanceProfile
    from cwltool.stdfsaccess import StdFsAccess

    from weaver.base import EnumType
    from weaver.datatype import Job
    from weaver.formats import AnyContentType, AnyOutputFormat
    from weaver.typedefs import URL, AnyKey, AnySettingsContainer

    AnyProvenanceFormat = Union[AnyContentType, "ProvenanceFormat"]


class ProvenancePathType(Constants):
    PROV = "/prov"
    PROV_INFO = "/prov/info"
    PROV_WHO = "/prov/who"
    PROV_INPUTS = "/prov/inputs"
    PROV_OUTPUTS = "/prov/outputs"
    PROV_RUN = "/prov/run"
    PROV_RUNS = "/prov/runs"

    @classmethod
    def types(cls):
        # type: () -> List[str]
        return [cls.as_type(prov) for prov in cls.values()]

    @classmethod
    def as_type(cls, prov):
        # type: (Any) -> Optional[str]
        prov = cls.get(prov)
        if isinstance(prov, str):
            return prov.rsplit("/", 1)[-1]
        return None

    @classmethod
    def get(            # pylint: disable=W0221,W0237  # arguments differ/renamed for clarity
        cls,
        prov,           # type: Union[AnyKey, EnumType, "ProvenancePathType"]
        default=None,   # type: Optional[Any]
        run_id=None,    # type: Optional[str]
    ):                  # type: (...) -> Optional["ProvenancePathType"]
        prov_found = super().get(prov)
        if prov_found is not None and run_id is None:
            return prov_found
        if isinstance(prov, str):
            if not prov_found and prov.strip("/") not in ProvenancePathType.types():
                return default
            prov = f"/{prov}" if not prov.startswith("/") else prov
            prov = f"/prov{prov}" if not prov.startswith("/prov") else prov
            if run_id:
                if prov.rsplit("/", 1)[-1] in ["run", "inputs", "outputs"]:
                    prov = f"{prov}/{run_id}"
                else:
                    return default
            return cast("ProvenancePathType", prov)
        return default


class ProvenanceFormat(Constants):
    PROV_JSON = "PROV-JSON"
    PROV_JSONLD = "PROV-JSONLD"
    PROV_XML = "PROV-XML"
    PROV_TURTLE = "PROV-TURTLE"
    PROV_N = "PROV-N"
    PROV_NT = "PROV-NT"
    PROV_OGC_JSON = "PROV-OGC-JSON"

    _media_types = {
        ContentType.APP_YAML: PROV_JSON,
        ContentType.APP_JSON: PROV_JSON,
        ContentType.APP_PROV_JSON: PROV_JSON,
        ContentType.APP_JSONLD: PROV_JSONLD,
        ContentType.TEXT_TURTLE: PROV_TURTLE,
        ContentType.TEXT_PROVN: PROV_N,
        ContentType.TEXT_XML: PROV_XML,
        ContentType.APP_XML: PROV_XML,
        ContentType.APP_PROV_XML: PROV_XML,
        ContentType.APP_NT: PROV_NT,
        ContentType.APP_PROV_OGC_JSON: PROV_OGC_JSON,
    }
    _rev_path_types = {_prov_type: _ctype for _ctype, _prov_type in _media_types.items()}
    _profiles = {
        ContentType.APP_YAML: "https://www.w3.org/submissions/prov-json/",
        ContentType.APP_JSON: "https://www.w3.org/submissions/prov-json/",
        ContentType.APP_PROV_JSON: "https://www.w3.org/submissions/prov-json/",
        ContentType.APP_JSONLD: "https://www.w3.org/submissions/prov-jsonld/",
        ContentType.TEXT_TURTLE: "https://www.w3.org/TR/prov-o/",
        ContentType.TEXT_PROVN: "https://www.w3.org/TR/prov-n/",
        ContentType.TEXT_XML: "https://www.w3.org/TR/prov-xml/",
        ContentType.APP_XML: "https://www.w3.org/TR/prov-xml/",
        ContentType.APP_PROV_XML: "https://www.w3.org/TR/prov-xml/",
        ContentType.APP_NT: "https://www.w3.org/TR/prov-o/",
        ContentType.APP_PROV_OGC_JSON: "https://docs.ogc.org/DRAFTS/26-038.html",
    }

    @classmethod
    def get(                        # pylint: disable=W0221,W0237  # arguments differ/renamed for clarity
        cls,
        prov_format,                # type: Optional[AnyProvenanceFormat]
        default=None,               # type: Optional[Any]
        allow_media_type=False,     # type: bool
    ):                              # type: (...) -> Optional["ProvenanceFormat"]
        prov = super().get(prov_format, default=default)
        if prov is None and allow_media_type:
            prov = cls._media_types.get(prov_format)
            return prov
        return prov

    @classmethod
    def media_types(cls):
        # type: () -> List[ContentType]
        return list(cls._media_types)

    @classmethod
    def formats(cls):
        # type: () -> List[Union[ProvenanceFormat, str]]
        return cls.values()

    @classmethod
    def as_media_type(cls, prov_format, output_format=None):
        # type: (Optional[AnyProvenanceFormat], Optional[AnyOutputFormat]) -> Optional[AnyContentType]
        ctype = cls._rev_path_types.get(prov_format)
        # specialize types when identified with known representations
        if ctype == ContentType.APP_JSON:
            ctype = ContentType.APP_PROV_JSON
        elif ctype in ContentType.ANY_XML:
            ctype = ContentType.APP_PROV_XML
        # YAML is not a distinct PROV representation on its own, but merely an alternate serialization of PROV-JSON.
        # When the desired 'output_format' is specifically YAML, request/report that exact media-type instead of the
        # generic PROV-JSON, such that the API can return the native YAML representation directly.
        if (
            ctype == ContentType.APP_PROV_JSON and
            OutputFormat.get(output_format) in [OutputFormat.YAML, OutputFormat.YML]
        ):
            ctype = ContentType.APP_YAML
        return ctype

    @classmethod
    def as_profile(cls, prov_format, output_format=None):
        # type: (Optional[AnyProvenanceFormat], Optional[AnyOutputFormat]) -> Optional[URL]
        ctype = cls.as_media_type(prov_format, output_format=output_format)
        return cls._profiles.get(ctype)

    @classmethod
    def resolve_compatible_formats(
        cls,
        prov,           # type: Optional[Union[ProvenancePathType, str]]
        prov_format,    # type: Optional[Union[ProvenanceFormat, str]]
        output_format,  # type: Optional[Union[OutputFormat, str]]
    ):                  # type: (...) -> Tuple[Optional[ProvenanceFormat], Optional[str]]
        """
        Resolves multiple :class:`OutputFormat` and :class:`ProvenanceFormat` combinations for compatible formats.

        Compatible formats depend on the PROV endpoint being requested.
        If output format is not specified, apply the corresponding PROV format that will work transparently.
        Otherwise, ensure they are aligned against the expected PROV endpoints and supported :term:`Media-Types`.

        :returns:
            Tuple of a resolved PROV format if only the output format was specified,
            and the relevant error detail if they are incompatible.
        """
        prov = ProvenancePathType.get(prov, default=ProvenancePathType.PROV)
        prov_format_requested = prov_format
        prov_format = ProvenanceFormat.get(prov_format, allow_media_type=True)
        default_format = output_format
        output_format = OutputFormat.get(output_format)

        # if an explicit PROV format was requested but could not be resolved, it is unsupported
        if prov_format_requested and prov_format is None:
            return None, f"PROV format '{prov_format_requested}' could not be identified or is not supported"

        # if default was originally falsy, it would have been replaced by 'JSON'
        # ignore it in this case to resolve any explicitly specified PROV format by itself
        if not output_format or not default_format:
            if prov == ProvenancePathType.PROV:
                prov_format = prov_format or ProvenanceFormat.PROV_JSON
            else:
                prov_format = None
            return prov_format, None

        out_fmt = output_format.split("+", 1)[0]
        err_mismatch = (
            None,
            f"output format '{output_format}' conflicts with PROV format '{prov_format}'"
        )

        # only main PROV endpoint supports alternate formats
        # all others are plain text only
        if prov not in [None, ProvenancePathType.PROV]:
            if out_fmt in [OutputFormat.TEXT, OutputFormat.TXT]:
                return None, None
            return err_mismatch

        if out_fmt in [OutputFormat.JSON, OutputFormat.YAML, OutputFormat.YML]:
            if prov_format not in [
                None,
                ProvenanceFormat.PROV_JSON,
                ProvenanceFormat.PROV_JSONLD,
                ProvenanceFormat.PROV_OGC_JSON,
            ]:
                return err_mismatch
            if prov_format is None:
                prov_format = ProvenanceFormat.PROV_JSON
            return prov_format, None

        if out_fmt in [OutputFormat.XML]:
            if prov_format not in [None, ProvenanceFormat.PROV_XML]:
                return err_mismatch
            if prov_format is None:
                prov_format = ProvenanceFormat.PROV_XML
            return prov_format, None

        if out_fmt in [OutputFormat.TEXT, OutputFormat.TXT]:
            if prov_format not in [
                None,
                ProvenanceFormat.PROV_N,
                ProvenanceFormat.PROV_NT,
                ProvenanceFormat.PROV_TURTLE,
            ]:
                return err_mismatch
            if prov_format is None:
                prov_format = ProvenanceFormat.PROV_N
            return prov_format, None

        return None, f"output format '{output_format}' does not have any PROV equivalent"


class WeaverResearchObject(ResearchObject):
    """
    Defines extended :term:`Provenance` details with `Weaver` operations and referencing the active server instance.
    """

    def __init__(self, job, settings, fs_access, temp_prefix_ro="tmp", orcid="", full_name=""):
        # type: (Job, AnySettingsContainer, StdFsAccess, str, str, str) -> None
        super(WeaverResearchObject, self).__init__(fs_access, temp_prefix_ro, orcid, full_name)

        # rewrite auto-initialized random UUIDs with Weaver-specific references
        self.job = job
        self.ro_uuid = job.uuid
        self.base_uri = f"arcp://uuid,{self.ro_uuid}/"
        self.settings = settings

    @staticmethod
    def sha1_uuid(document, identifier):
        # type: (ProvDocument, str) -> str
        """
        Generate a prefixed SHA1 hash from the identifier value.
        """
        sha1_ns = document._namespaces[cwl_prov_const.DATA]
        sha1_id = f"{sha1_ns.prefix}:{hashlib.sha1(identifier.encode(), usedforsecurity=False).hexdigest()}"
        return sha1_id

    def initialize_provenance(self, full_name, host_provenance, user_provenance, orcid, fsaccess, run_uuid=None):
        # type: (str, bool, bool, str, StdFsAccess, Optional[UUID]) -> ProvenanceProfile
        """
        Hook `Weaver` metadata onto user provenance step.
        """
        prov_profile = super(WeaverResearchObject, self).initialize_provenance(
            full_name=full_name,
            host_provenance=host_provenance,
            user_provenance=user_provenance,
            orcid=orcid,
            fsaccess=fsaccess,
            run_uuid=run_uuid,
        )
        document = prov_profile.document

        # following agents are expected to exist (created by inherited class)
        user_uuid = self.orcid or cwl_prov_const.USER_UUID
        user_agent = document.get_record(user_uuid)[0]
        wf_agent = document.get_record(self.engine_uuid)[0]  # current job run aligned with cwl workflow

        doi_ns = document.add_namespace("doi", "https://doi.org/")

        weaver_full_name = f"crim-ca/weaver:{weaver_version}"
        weaver_code_url = "https://github.com/crim-ca/weaver"
        weaver_code_sha1 = self.sha1_uuid(document, weaver_code_url)
        weaver_code_entity = document.entity(
            weaver_code_sha1,
            {
                prov_const.PROV_TYPE: prov_const.PROV["PrimarySource"],
                prov_const.PROV_LABEL: "Source code repository",
                prov_const.PROV_LOCATION: weaver_code_url,
            },
        )

        weaver_url = get_weaver_url(self.settings)
        weaver_desc = self.settings.get(
            "weaver.wps_metadata_identification_abstract",
            "Weaver OGC API Processes Server"
        )
        weaver_instance_sha1 = self.sha1_uuid(document, weaver_url)
        weaver_instance_meta = [
            (prov_const.PROV_TYPE, prov_const.PROV["SoftwareAgent"]),
            (prov_const.PROV_LOCATION, weaver_url),
            (prov_const.PROV_LABEL, weaver_desc),
            (prov_const.PROV_LABEL, weaver_full_name),
            (prov_const.PROV_ATTR_GENERAL_ENTITY, weaver_code_sha1),
            (prov_const.PROV_ATTR_SPECIFIC_ENTITY, f"{doi_ns.prefix}:10.5281/zenodo.14210717"),  # see CITATION.cff
        ]
        weaver_instance_agent = document.agent(weaver_instance_sha1, weaver_instance_meta)

        crim_name = "Computer Research Institute of Montréal"
        crim_sha1 = self.sha1_uuid(document, crim_name)
        crim_entity = document.entity(
            crim_sha1,
            {
                prov_const.PROV_TYPE: prov_const.PROV["Organization"],
                cwl_prov_const.FOAF["name"]: crim_name,
                cwl_prov_const.SCHEMA["name"]: crim_name,
            }
        )

        server_provider_name = self.settings.get("weaver.wps_metadata_provider_name")
        server_provider_url = self.settings.get("weaver.wps_metadata_provider_url")
        server_provider_meta = []
        server_provider_entity = None
        if server_provider_name:
            server_provider_meta.extend([
                (cwl_prov_const.FOAF["name"], server_provider_name),
                (cwl_prov_const.SCHEMA["name"], server_provider_name),
            ])
        if server_provider_url:
            server_provider_meta.extend([
                (prov_const.PROV_LOCATION, server_provider_url),
            ])
        if server_provider_meta:
            server_provider_id = server_provider_url or server_provider_name
            server_provider_sha1 = self.sha1_uuid(document, server_provider_id)
            server_provider_meta.extend([
                (prov_const.PROV_TYPE, prov_const.PROV["Organization"]),
                (prov_const.PROV_LABEL, "Server Provider"),
            ])
            server_provider_entity = document.entity(
                server_provider_sha1,
                server_provider_meta,
            )

        proc_url = self.job.process_url(self.settings)
        proc_id = f"{self.job.service}:{self.job.process}" if self.job.service else self.job.process
        proc_uuid = f"{weaver_instance_sha1}:{proc_id}"
        proc_sha1 = self.sha1_uuid(document, proc_uuid)
        proc_entity = document.entity(
            proc_sha1,
            {
                prov_const.PROV_TYPE: cwl_prov_const.WFDESC["Process"],
                prov_const.PROV_LOCATION: proc_url,
                prov_const.PROV_LABEL: "Process Description",
            }
        )

        # NOTE: Since prov 3.0.0 enforces PROV-CONSTRAINTS, this must
        # be an activity, not an entity, as it shares the ID of the
        # WorkflowRun.
        job_url = self.job.job_url(self.settings)
        job_activity = document.activity(
            self.job.uuid.urn,
            other_attributes={
                prov_const.PROV_TYPE: cwl_prov_const.WFPROV["ProcessRun"],
                prov_const.PROV_LOCATION: job_url,
                prov_const.PROV_LABEL: "Job Information",
                cwl_prov_const.WFPROV["wasEnactedBy"]: wf_agent,
                cwl_prov_const.WFPROV["describedByProcess"]: proc_entity,
            }
        )
        # Add a wasStartedBy relation (this is redundant for
        # single-process jobs, but will unify in RDF or JSONLD)
        document.wasStartedBy(activity=job_activity, starter=wf_agent)

        # NOTE: This is a somewhat fragile workaround for cwlprov
        # unconditionally creating the user agent as a Person.  The
        # intent of PROV is that records should be update-only to
        # ensure their integrity, but the only other way to solve this
        # would be to duplicate all of the functionality in
        # `ResearchObject.user_provenance`.
        user_types = user_agent._attributes[prov_const.PROV_TYPE]
        user_types.discard(prov_const.PROV["Person"])
        user_types.discard(cwl_prov_const.SCHEMA["Person"])
        user_types.add(prov_const.PROV["SoftwareAgent"])
        user_types.add(cwl_prov_const.SCHEMA["SoftwareApplication"])

        # Define PROV relations
        document.hadPrimarySource(generatedEntity=weaver_instance_agent, usedEntity=weaver_code_entity)
        document.actedOnBehalfOf(delegate=weaver_instance_agent, responsible=user_agent)
        document.wasAttributedTo(entity=crim_entity, agent=weaver_code_entity)
        if server_provider_entity:
            document.wasDerivedFrom(generatedEntity=server_provider_entity,
                                    usedEntity=weaver_instance_agent)
            document.wasAttributedTo(entity=server_provider_entity, agent=weaver_instance_agent)

        return prov_profile

    def resolve_user(self):
        # type: () -> Tuple[str, str]
        """
        Override :mod:`cwltool.cwlprov` default machine user.

        It is expected that the :term:`CWL` runner will executed by the ``weaver-worker`` (i.e.: via :mod:`celery`).
        Define a generic user to avoid exposing implementation-specific "OS" user that will not be informative
        for the generated :term:`Provenance`. Using a distinct name than just "_Weaver_" allows preserving the
        distinction between the :term:`API` _agent_ and the "user" _agent_ for which :term:`Job` execution is
        acted on behalf between these _agent_ endoffs.

        .. seealso::
            :ref:`running-execution-details`
        """
        weaver_short_name = "weaver-worker"
        weaver_full_name = f"{weaver_short_name}@crim-ca/weaver:{weaver_version}"
        return weaver_short_name, weaver_full_name

    def resolve_host(self):
        # type: () -> Tuple[str, str]
        """
        Override :mod:`cwltool` default machine host.
        """
        weaver_url = get_weaver_url(self.settings)
        weaver_fqdn = urlparse(weaver_url).hostname
        return weaver_fqdn, weaver_url


class RelationHandler(NamedTuple):
    """
    Mapping of PROV relations to OGC Provenance Chain JSON properties.

    Forward and inverse relations are provided to allow rooted graphs
    to be built in the "object" form of OGC Provenance.  Some inverse
    relations are not officially part of PROV-O but "recommended" for
    specific implementation cases such as this one. These are defined
    in https://www.w3.org/ns/prov-o-inverses and were extracted with
    the following SPARQL query:

        SELECT ?rel ?inv WHERE { ?inv owl:inverseOf ?rel }

    The `subject_role` and `object_role` are reversed for the inverse
    relations.

    """
    forward: str
    inverse: str
    subject_role: str
    object_role: str


_RELATION_HANDLERS = {
    prov_const.PROV_GENERATION: RelationHandler("wasGeneratedBy", "generated",
                                                "entity", "activity"),
    prov_const.PROV_USAGE: RelationHandler("used", "wasUsedBy", "activity", "entity"),
    prov_const.PROV_ASSOCIATION: RelationHandler("wasAssociatedWith", "wasAssociateFor",
                                                 "activity", "agent"),
    prov_const.PROV_ATTRIBUTION: RelationHandler("wasAttributedTo", "contributed",
                                                 "entity", "agent"),
    prov_const.PROV_DERIVATION: RelationHandler("wasDerivedFrom", "hadDerivation",
                                                "generatedEntity", "usedEntity"),
    prov_const.PROV_DELEGATION: RelationHandler("actedOnBehalfOf", "hadDelegate",
                                                "delegate", "responsible"),
    prov_const.PROV_SPECIALIZATION: RelationHandler("generalEntity", "specificEntity",
                                                    "specificEntity", "generalEntity"),
}
_RELATION_FIELDS = set([*(h.forward for h in _RELATION_HANDLERS.values()),
                        *(h.inverse for h in _RELATION_HANDLERS.values())])
_OBJECT_TYPES = {
    "Entity",
    "Activity",
    "Agent",
}
_PROV_ATTRS = (("startTime", prov_const.PROV_ATTR_STARTTIME),
               ("endTime", prov_const.PROV_ATTR_ENDTIME),
               ("time", prov_const.PROV_ATTR_TIME),
               ("location", prov_const.PROV_LOCATION))


def _prov_value(value):
    # type: (Any) -> Any
    """
    Convert a PROV attribute value into a JSON-serializable representation.
    """
    if isinstance(value, (QualifiedName, Identifier)):
        return value.uri
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _ogc_prov_objects(document):
    # type: (ProvDocument) -> dict[str, dict[str, Any]]
    objects_by_uri = {}  # type: dict[str, dict[str, Any]]
    for record in document.get_records():
        record_type = record.get_type().localpart if record.get_type() else None
        if record_type not in _OBJECT_TYPES:  # only objects in the OGC schema
            continue
        if record.identifier is None:
            continue
        key = record.identifier.uri
        if key in objects_by_uri:
            continue
        objects_by_uri[key] = {"id": key, "provType": record_type}
        if record.value:
            objects_by_uri[key]["value"] = list(record.value)
        if record.label != record.identifier:
            objects_by_uri[key]["label"] = record.label
        prov_types = [str(val) for val in record.get_attribute(prov_const.PROV_TYPE)]
        if prov_types:
            objects_by_uri[key]["prov:type"] = prov_types[0] if len(prov_types) == 1 else prov_types
        for attr, prov_attr in _PROV_ATTRS:
            values = [_prov_value(val) for val in record.get_attribute(prov_attr)]
            if values:
                objects_by_uri[key][attr] = values[0] if len(values) == 1 else values
    return objects_by_uri


def _ogc_prov_nested(objects_by_uri, root_obj, expanded):
    # type: (dict[str, dict[str, Any]], dict[str, Any], set[str]) -> dict[str, Any]
    for attr, vals in root_obj.items():
        if attr not in _RELATION_FIELDS:
            continue
        if isinstance(vals, str):
            vals = [vals]
        for idx, uri in enumerate(vals):
            if not isinstance(uri, str):
                continue
            obj = objects_by_uri.get(uri)
            if uri in expanded or obj is None:
                continue
            expanded.add(uri)
            vals[idx] = _ogc_prov_nested(objects_by_uri, obj, expanded)
        root_obj[attr] = vals[0] if len(vals) == 1 else vals
    return root_obj


def convert_to_prov_chain(input_data, root_uri=None):
    # type: (str, str | None) -> str
    """Convert a PROV-JSON document (as text) to OGC Provenance Chain JSON.

    Since OGC Provenance Chain has no notion of bundles, this operates
    on the flattened PROV document.  Only objects and relations
    defined in the schema are considered:

    - Entity
    - Activity
    - Agent
    - Generation
    - Usage
    - Association
    - Attribution
    - Derivation
    - Delegation

    Certain PROV attributes are also supported:

    - prov:type (contains extra types not specified in ``provType``)
    - startTime
    - endTime
    - time
    - location
    - label
    - value

    :param root_uri: If not ``None``, return object provenance rooted
        at the object with the given URI.  Otherwise, return
        array-form provenance for all objects.
    :return: OGC Provenance Chain in array or object form, according
        to the value of `root_uri`.

    .. seealso::
        - `OGC Provenance Chain Schemas <https://ogcincubator.github.io/bblock-prov-schema/>_`
    """
    document = ProvDocument.deserialize(content=input_data, format="json")
    objects_by_uri = _ogc_prov_objects(document)
    # Fail fast if an unknown root URI is requested
    root_obj = None
    if root_uri is not None:
        root_obj = objects_by_uri.get(root_uri)
        if root_obj is None:
            raise ValueError(f"Requested root object {root_uri} not found in PROV document")

    def _resolve_relation(prov, prop, uri):
        # type: (dict[str, Any], str, str) -> None
        existing = prov.get(prop)
        if existing is None:
            prov[prop] = uri
        elif isinstance(existing, list):
            if uri not in existing:
                existing.append(uri)
        elif existing != uri:
            prov[prop] = [existing, uri]

    # Add recognized relations to recognized subjects
    for record in document.get_records(ProvRelation):
        handler = _RELATION_HANDLERS.get(record.get_type())
        if handler is None:
            continue
        # Resolve attributes to QNames using local part (assume prefix is prov)
        formal = {key.localpart: value for key, value in record.formal_attributes}
        subj = formal.get(handler.subject_role)
        if subj is None:
            continue
        obj = formal.get(handler.object_role)
        if obj is None:
            continue
        # For list form, resolve only forward relations for subjects
        subj_prov = objects_by_uri.get(subj.uri)
        if subj_prov is None:
            # Relation referencing a record not declared in this document
            continue
        _resolve_relation(subj_prov, handler.forward, obj.uri)
        if root_obj is None:
            continue
        # For object form, resolve inverse relations for objects as well
        obj_prov = objects_by_uri.get(obj.uri)
        if obj_prov is None:
            # Relation referencing a record not declared in this document
            continue
        _resolve_relation(obj_prov, handler.inverse, subj.uri)

    if root_obj is not None:
        # Object form: Traverse graph depth-first in document order
        # replacing the first instance of an URI reference within this
        # document with the object it references.
        expanded = set()
        assert root_uri is not None  # hello mypy, we checked it above
        expanded.add(root_uri)
        return json.dumps(_ogc_prov_nested(objects_by_uri, root_obj, expanded))
    else:
        # List form: Output resolved objects in document order
        return json.dumps([objects_by_uri[key] for key in objects_by_uri])
