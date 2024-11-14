import json
import os
import shutil
import tarfile
import tempfile

from celery.utils.log import get_task_logger

LOGGER = get_task_logger(__name__)


def is_image(i):
    return i.lower().endswith((".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif"))


def is_svg(i):
    return i.lower().endswith(".svg")


def is_png(i):
    return i.lower().endswith(".png")


def is_tiff(i):
    return i.lower().endswith(".tif") or i.lower().endswith(".tiff")


def is_gif(i):
    return i.lower().endswith(".gif")


def get_content(file_path, mode="r"):
    with open(file_path, mode, encoding="utf-8") as f:
        return f.read()


def write_content(file_path, content):
    if isinstance(content, dict):
        content = json.dumps(content)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)


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


def write_images(images, output_file, ext="png"):
    with tempfile.TemporaryDirectory() as tmp_path:
        img_paths = []
        for i, img in enumerate(images):
            img_path = os.path.join(tmp_path, f"{str(i).zfill(4)}.{ext}")
            img.save(img_path)
            img_paths.append(img_path)
        if len(img_paths) > 1:
            if not output_file.endswith(".tar.gz"):
                output_file += ".tar.gz"
            with tarfile.open(output_file, "w:gz") as tar:
                for img_path in img_paths:
                    tar.add(img_path, arcname=os.path.basename(img_path))
        else:
            shutil.copy(img_paths[0], output_file)
