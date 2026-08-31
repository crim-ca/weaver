"""
Definitions related to :term:`Provenance` features and the :term:`W3C` ``PROV`` specification.
"""
import hashlib
from typing import TYPE_CHECKING, cast
from urllib.parse import urlparse

from cwltool.cwlprov import provenance_constants as cwl_prov_const
from cwltool.cwlprov.ro import ResearchObject
from prov import constants as prov_const

from weaver.__meta__ import __version__ as weaver_version
from weaver.base import Constants
from weaver.formats import ContentType, OutputFormat
from weaver.utils import get_weaver_url

if TYPE_CHECKING:
    from typing import Any, List, Optional, Tuple, Union
    from uuid import UUID

    from cwltool.cwlprov.provenance_profile import ProvenanceProfile
    from cwltool.stdfsaccess import StdFsAccess
    from prov.model import ProvDocument

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
            if prov_format not in [None, ProvenanceFormat.PROV_JSON, ProvenanceFormat.PROV_JSONLD]:
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

        job_entity = document.entity(
            self.job.uuid.urn,
            {
                prov_const.PROV_TYPE: cwl_prov_const.WFDESC["ProcessRun"],
                prov_const.PROV_LOCATION: self.job.job_url(self.settings),
                prov_const.PROV_LABEL: "Job Information",
            }
        )
        proc_url = self.job.process_url(self.settings)
        proc_id = f"{self.job.service}:{self.job.process}" if self.job.service else self.job.process
        proc_uuid = f"{weaver_instance_sha1}:{proc_id}"
        proc_entity = document.entity(
            proc_uuid,
            {
                prov_const.PROV_TYPE: cwl_prov_const.WFDESC["Process"],
                prov_const.PROV_LOCATION: proc_url,
                prov_const.PROV_LABEL: "Process Description",
            }
        )

        # following agents are expected to exist (created by inherited class)
        cwltool_agent = document.get_record(cwl_prov_const.ACCOUNT_UUID)[0]
        user_uuid = self.orcid or cwl_prov_const.USER_UUID
        user_agent = document.get_record(user_uuid)[0]
        wf_agent = document.get_record(self.engine_uuid)[0]  # current job run aligned with cwl workflow

        # adjust user agent as software rather than person (see 'resolve_user'), and leave any other types untouched
        user_types = cast(set, user_agent.get_attribute(prov_const.PROV_TYPE))
        user_types.symmetric_difference_update({
            prov_const.PROV["Person"],
            cwl_prov_const.SCHEMA["Person"],
            prov_const.PROV["SoftwareAgent"],
            cwl_prov_const.SCHEMA["SoftwareApplication"],
        })

        # define relationships cross-references: https://wf4ever.github.io/ro/wfprov.owl
        document.primary_source(weaver_instance_agent, weaver_code_entity)
        document.actedOnBehalfOf(weaver_instance_agent, user_agent)
        document.specializationOf(weaver_instance_agent, cwltool_agent)
        document.attribution(crim_entity, weaver_code_entity)
        document.wasDerivedFrom(cwltool_agent, weaver_instance_agent)
        document.wasStartedBy(job_entity, weaver_instance_agent)
        document.wasStartedBy(wf_agent, job_entity, time=self.job.created)
        document.specializationOf(wf_agent, job_entity)
        document.alternateOf(wf_agent, job_entity)
        document.wasGeneratedBy(job_entity, proc_entity)
        if server_provider_entity:
            document.derivation(server_provider_entity, weaver_instance_agent)
            document.attribution(server_provider_entity, weaver_instance_agent)

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
