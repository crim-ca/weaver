import json
import os

from celery.utils.log import get_task_logger

LOGGER = get_task_logger(__name__)


def is_image(i):
    return i.lower().endswith(('.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp', '.gif', '.svg'))


def is_svg(i):
    return i.lower().endswith(".svg")


def is_png(i):
    return i.lower().endswith(".png")


def is_tif(i):
    return i.lower().endswith(".tif") or i.lower().endswith(".tiff")


def is_gif(i):
    return i.lower().endswith(".gif")


def get_content(fp, t="r"):
    with open(fp, t) as f:
        return f.read()


def write_content(fp, content):
    if isinstance(content, dict):
        content = json.dumps(content)

    with open(fp, "w") as xml_file:
        xml_file.write(content)


def get_file_extension(filename, dot=True):
    # type: (str, bool) -> str
    """
    Retrieves the extension corresponding to :paramref:`mime_type` if explicitly defined, or by parsing it.
    """

    def _handle_dot(_ext):
        # type: (str) -> str
        if dot and not _ext.startswith(".") and _ext:  # don't add for empty extension
            return f".{_ext}"
        if not dot and _ext.startswith("."):
            return _ext[1:]
        return _ext

    ext = os.path.splitext(filename.lower())[1]
    return _handle_dot(ext)
