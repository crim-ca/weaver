import json
import os
import shutil
import tarfile
import tempfile
from typing import List, Union

from celery.utils.log import get_task_logger
from PIL import Image
from processes.convert import get_field

LOGGER = get_task_logger(__name__)


def is_image(i: str) -> bool:
    """
    Check if the file is an image based on its extension.

    Args:
        i (str): The file name or path.

    Returns:
        bool: True if the file is an image, False otherwise.
    """
    return i.lower().endswith((".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif"))


def is_svg(i: str) -> bool:
    """
    Check if the file is an SVG image.

    Args:
        i (str): The file name or path.

    Returns:
        bool: True if the file is an SVG, False otherwise.
    """
    return i.lower().endswith(".svg")


def is_png(i: str) -> bool:
    """
    Check if the file is a PNG image.

    Args:
        i (str): The file name or path.

    Returns:
        bool: True if the file is PNG, False otherwise.
    """
    return i.lower().endswith(".png")


def is_tiff(i: str) -> bool:
    """
    Check if the file is a TIFF image.

    Args:
        i (str): The file name or path.

    Returns:
        bool: True if the file is TIFF, False otherwise.
    """
    return i.lower().endswith(".tif") or i.lower().endswith(".tiff")


def is_gif(i: str) -> bool:
    """
    Check if the file is a GIF image.

    Args:
        i (str): The file name or path.

    Returns:
        bool: True if the file is GIF, False otherwise.
    """
    return i.lower().endswith(".gif")


def get_content(file_path: str, mode: str = "r") -> str:
    """
    Retrieve the content of a file.

    Args:
        file_path (str): The path to the file.
        mode (str, optional): The mode in which to open the file. Defaults to "r".

    Returns:
        str: The content of the file as a string.
    """
    with open(file_path, mode, encoding="utf-8") as f:
        return f.read()


def write_content(file_path: str, content: Union[str, dict]) -> None:
    """
    Write content to a file.

    Args:
        file_path (str): The path to the file.
        content (Union[str, dict]): The content to write, can be a string or dictionary.
    """
    if isinstance(content, dict):
        content = json.dumps(content)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)


def write_images(images: List[Image.Image], output_file: str, ext: str = "png") -> None:
    """
    Save a list of images to an archive or single file.

    Args:
        images (List[Image.image]): A list of images to save.
        output_file (str): The output file name or path.
        ext (str, optional): The image format (extension). Defaults to "png".
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

    Args:
        formats (List[Dict[str, str]]): A list of format dictionaries containing
            the "mediaType" key.
        conversion_dict (dict[str, list[str]]): A dictionary mapping media types
            to their alternate formats.

    Returns:
        List[Dict[str, str]]: The extended list of formats with alternate formats
            added in a consistent order.
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
