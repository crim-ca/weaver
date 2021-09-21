"""
Define a default XML parser that avoids XXE injection.

Package :mod:`lxml` is employed directly even though some linters (e.g.: ``bandit``) report to employ ``defusedxml``
instead, because that package's extension with ``lxml`` is marked as deprecated.

.. seealso::
    https://pypi.org/project/defusedxml/#defusedxml-lxml

To use the module, import is as if importing ``lxml.etree``:

.. code-block:: python

    from weaver.xml_util import XML  # ElementTree
    from weaver import xml_util

    data = xml_util.fromstring("<xml>content</xml>")
"""

from lxml import etree  # nosec: B410  # flagged issue is known, this is what the applied fix below is about

# security fix: XML external entity (XXE) injection
#   https://lxml.de/parsing.html#parser-options
#   https://nvd.nist.gov/vuln/detail/CVE-2021-39371
# based on:
#   https://github.com/geopython/pywps/pull/616
XML_PARSER = etree.XMLParser(
    resolve_entities=False,
)

tostring = etree.tostring
Element = etree.Element

# define this type here so that code can use it for actual logic without repeating 'noqa'
XML = etree._Element  # noqa


def fromstring(text):
    return etree.fromstring(text, parser=XML_PARSER)  # nosec: B410


def parse(source):
    return etree.parse(source, parser=XML_PARSER)  # nosec: B410
