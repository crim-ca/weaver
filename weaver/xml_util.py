"""
Define a default XML parser that avoids XXE injection.

Package :mod:`lxml` is employed directly even though some linters (e.g.: ``bandit``) report to employ ``defusedxml``
instead, because that package's extension with :mod:`lxml` is marked as deprecated.

.. seealso::
    https://pypi.org/project/defusedxml/#defusedxml-lxml

To use the module, import is as if importing :mod:`lxml.etree`:

.. code-block:: python

    from weaver.xml_util import XML  # ElementTree
    from weaver import xml_util

    data = xml_util.fromstring("<xml>content</xml>")
"""
from typing import TYPE_CHECKING

from bs4.builder._lxml import LXMLTreeBuilder  # noqa: W0212
from lxml import etree as lxml_etree  # nosec: B410  # flagged known issue, this is what the applied fix below is about
from owslib.wps import etree as owslib_wps_etree

if TYPE_CHECKING:
    from io import BufferedReader
    from typing import Any, AnyStr, Union


XML_PARSER = lxml_etree.XMLParser(
    # security fix: XML external entity (XXE) injection
    #   https://lxml.de/parsing.html#parser-options
    #   https://nvd.nist.gov/vuln/detail/CVE-2021-39371
    # based on:
    #   https://github.com/geopython/pywps/pull/616
    resolve_entities=False,
    # avoid failing parsing if some characters are not correctly escaped
    # based on:
    #   https://stackoverflow.com/a/57450722/5936364
    recover=True,  # attempt, no guarantee
)

tostring = lxml_etree.tostring
Element = lxml_etree.Element
ParseError = lxml_etree.ParseError

# define this type here so that code can use it for actual logic without repeating 'noqa'
XML = lxml_etree._Element  # noqa

# save a local reference to method employed by OWSLib directly called
_lxml_fromstring = lxml_etree.fromstring


def fromstring(text, parser=XML_PARSER):
    # type: (AnyStr, lxml_etree.XMLParser) -> XML
    from weaver.utils import str2bytes

    return _lxml_fromstring(str2bytes(text), parser=parser)  # nosec: B410


def parse(source, parser=XML_PARSER):
    # type: (Union[str, BufferedReader], lxml_etree.XMLParser) -> XML
    return lxml_etree.parse(source, parser=parser)  # nosec: B410


# override OWSLib call with adjusted method reference with configured parser enforced
owslib_wps_etree.fromstring = fromstring


HTML = lxml_etree.HTML


def _lxml_tree_parser_maker(**parser_kwargs):
    # type: (**Any) -> lxml_etree.HTMLParser
    """
    Generate the XML/HTML tree parser.

    Uses similar parameters as in :meth:`bs4.builder._lxml.LXMLTreeBuilderForXML.default_parser`,
    but overriding some other options to make it more secure.

    Without this modification, the builder is usually created using:

    .. code-block:: python

        etree.XMLParser(target=self, strip_cdata=False, recover=True, encoding=encoding)
    """
    parser_kwargs.update({
        "no_network": True,
        "remove_pis": True,
        "huge_tree": False,
        "strip_cdata": True,
        "recover": True,
    })
    return lxml_etree.HTMLParser(**parser_kwargs)


HTML_PARSER = _lxml_tree_parser_maker()
HTML_TREE_BUILDER = LXMLTreeBuilder(parser=_lxml_tree_parser_maker)
LXML_TREE_BUILDER = HTML_TREE_BUILDER
