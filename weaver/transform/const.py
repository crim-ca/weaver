"""
Transformation constants.

This module contains constant definitions used across the transformation module,
separated to avoid circular import dependencies.
"""
from weaver.formats import ContentType

CONVERSION_DICT = {
    ContentType.TEXT_PLAIN: [ContentType.TEXT_PLAIN, ContentType.TEXT_HTML, ContentType.APP_PDF],
    ContentType.TEXT_HTML: [ContentType.TEXT_PLAIN, ContentType.APP_PDF],
    ContentType.IMAGE_PNG: [ContentType.IMAGE_GIF, ContentType.IMAGE_JPEG, ContentType.IMAGE_TIFF,
                            ContentType.IMAGE_SVG_XML, ContentType.APP_PDF],
    ContentType.IMAGE_GIF: [ContentType.IMAGE_PNG, ContentType.IMAGE_JPEG, ContentType.IMAGE_TIFF,
                            ContentType.IMAGE_SVG_XML, ContentType.APP_PDF],
    ContentType.IMAGE_JPEG: [ContentType.IMAGE_PNG, ContentType.IMAGE_GIF, ContentType.IMAGE_TIFF,
                             ContentType.IMAGE_SVG_XML, ContentType.APP_PDF],
    ContentType.IMAGE_TIFF: [ContentType.IMAGE_PNG, ContentType.IMAGE_GIF, ContentType.IMAGE_JPEG,
                             ContentType.IMAGE_SVG_XML, ContentType.APP_PDF],
    ContentType.IMAGE_SVG_XML: [ContentType.IMAGE_PNG, ContentType.IMAGE_GIF, ContentType.IMAGE_JPEG,
                                ContentType.IMAGE_TIFF, ContentType.APP_PDF],
    ContentType.TEXT_CSV: [ContentType.APP_XML, ContentType.APP_YAML, ContentType.APP_JSON],
    ContentType.APP_XML: [ContentType.APP_YAML, ContentType.APP_JSON],
    ContentType.APP_YAML: [ContentType.TEXT_CSV, ContentType.APP_XML, ContentType.APP_JSON],
    ContentType.APP_JSON: [ContentType.TEXT_CSV, ContentType.APP_XML, ContentType.APP_YAML]
}
EXCLUDED_TYPES = {ContentType.APP_RAW_JSON, ContentType.APP_OCTET_STREAM, ContentType.TEXT_PLAIN}
