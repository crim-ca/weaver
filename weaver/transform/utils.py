import json
import os
import shutil
import tarfile
import tempfile
from typing import List, Union

from celery.utils.log import get_task_logger
from PIL import Image
from processes.convert import get_field
from weaver.formats import ContentType, get_content_type

LOGGER = get_task_logger(__name__)


def is_image(image: str) -> bool:
    """
    Check if the file is an image based on its MIME content type.

    :param image: The file name or path.
    :return: True if the file is an image, False otherwise.
    """
    ext = os.path.splitext(image)[1]
    content_type = get_content_type(ext)
    return content_type.startswith("image/")


def is_svg(image: str) -> bool:
    """
    Check if the file is an SVG image based on its MIME content type.

    :param image: The file name or path.
    :return: True if the file is SVG, False otherwise.
    """
    ext = os.path.splitext(image)[1]
    return get_content_type(ext) == ContentType.IMAGE_SVG_XML


def is_png(image: str) -> bool:
    """
    Check if the file is a PNG image based on its MIME content type.

    :param image: The file name or path.
    :return: True if the file is PNG, False otherwise.
    """
    ext = os.path.splitext(image)[1]
    return get_content_type(ext) == ContentType.IMAGE_PNG


def is_tiff(image: str) -> bool:
    """
    Check if the file is a TIFF image based on its MIME content type.

    :param image: The file name or path.
    :return: True if the file is TIFF, False otherwise.
    """
    ext = os.path.splitext(image)[1]
    return get_content_type(ext) in {
        ContentType.IMAGE_TIFF,
        ContentType.IMAGE_GEOTIFF,
        ContentType.IMAGE_OGC_GEOTIFF,
        ContentType.IMAGE_COG,
    }


def is_gif(image: str) -> bool:
    """
    Check if the file is a GIF image based on its MIME content type.

    :param image: The file name or path.
    :return: True if the file is GIF, False otherwise.
    """
    ext = os.path.splitext(image)[1]
    return get_content_type(ext) == ContentType.IMAGE_GIF


def get_content(file_path: str, mode: str = "r") -> str:
    """
    Retrieve the content of a file.

    :param file_path: The path to the file.
    :param mode: The mode in which to open the file. Defaults to "r".
    :return: The content of the file as a string.
    """
    with open(file_path, mode, encoding="utf-8") as f:
        return f.read()


def write_content(file_path: str, content: Union[str, dict]) -> None:
    """
    Write content to a file.

    :param file_path: The path to the file.
    :param content: The content to write, can be a string or dictionary.
    """
    if isinstance(content, dict):
        content = json.dumps(content)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)


def write_images(images: List[Image.Image], output_file: str, ext: str = "png") -> None:
    """
    Save a list of images to an archive or single file.

    :param images: A list of images to save.
    :param output_file: The output file name or path.
    :param ext: The image format (extension). Defaults to "png".
    """
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


def extend_alternate_formats(formats, conversion_dict):
    """
    Extend a list of formats with missing alternate formats while preserving the original order.

    :param formats: A list of format dictionaries containing the "mediaType" key.
    :param conversion_dict: A dictionary mapping media types to their alternate formats.
    :return: The extended list of formats with alternate formats added in a consistent order.
    """
    if not formats or not all(isinstance(fmt, dict) for fmt in formats):
        return formats  # No formats or invalid structure, return as-is

    # Extract existing media types while preserving order
    existing_media_types = []
    seen = set()
    for format_entry in formats:
        media_type = get_field(format_entry, "mediaType", search_variations=True)
        if media_type and media_type not in seen:
            existing_media_types.append(media_type)
            seen.add(media_type)

    # Collect missing alternate formats while preserving original order
    missing_formats = []
    for media_type in existing_media_types:
        for alt_format in conversion_dict.get(media_type, []):
            if alt_format not in seen:
                missing_formats.append({"mediaType": alt_format})
                seen.add(alt_format)

    return formats + missing_formats
