import os
import tarfile
import tempfile

import pytest
from PIL import Image

from weaver.transform.utils import write_images

# pylint: disable=redefined-outer-name


@pytest.fixture(scope="module")
def test_sample_images():
    """
    Generate a reusable list of sample images for tests.
    """
    images = []
    for color in [(255, 0, 0), (0, 255, 0), (0, 0, 255)]:
        img = Image.new("RGB", (10, 10), color)
        images.append(img)
    return images


def test_write_images_multiple_images(test_sample_images):
    with tempfile.NamedTemporaryFile(suffix=".tar.gz") as temp_file_multi:
        write_images(test_sample_images, temp_file_multi.name)
        assert tarfile.is_tarfile(temp_file_multi.name)
        with tarfile.open(temp_file_multi.name, "r:gz") as tar:
            members = tar.getmembers()
            assert len(members) == len(test_sample_images)
            for i, member in enumerate(members):
                assert member.name == f"{str(i).zfill(4)}.png"


def test_write_images_single_image(test_sample_images):
    single_image = test_sample_images[:1]
    with tempfile.NamedTemporaryFile(suffix=".png") as temp_file_single:
        write_images(single_image, temp_file_single.name)
        assert os.path.isfile(temp_file_single.name)
        assert not tarfile.is_tarfile(temp_file_single.name)


def test_write_images_custom_extension(test_sample_images):
    with tempfile.NamedTemporaryFile(suffix=".jpg") as temp_file_custom:
        output_tar_path = f"{temp_file_custom.name}.tar.gz"
        try:
            write_images(test_sample_images, temp_file_custom.name, ext="jpg")
            assert tarfile.is_tarfile(output_tar_path)
            with tarfile.open(output_tar_path, "r:gz") as tar:
                members = tar.getmembers()
                assert len(members) == len(test_sample_images)
                for i, member in enumerate(members):
                    assert member.name == f"{str(i).zfill(4)}.jpg"
        finally:
            if os.path.exists(output_tar_path):
                os.remove(output_tar_path)


def test_write_images_output_file_naming(test_sample_images):
    with tempfile.NamedTemporaryFile(suffix=".output") as temp_file_naming:
        write_images(test_sample_images, temp_file_naming.name)
        expected_output = f"{temp_file_naming.name}.tar.gz"
        assert os.path.isfile(expected_output)
        assert tarfile.is_tarfile(expected_output)
