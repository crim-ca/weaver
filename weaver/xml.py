from lxml import etree

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
    return etree.fromstring(text, parser=XML_PARSER)


def parse(source):
    return etree.parse(source, parser=XML_PARSER)
