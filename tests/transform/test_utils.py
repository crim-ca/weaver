import os
import tarfile
import tempfile

from PIL import Image
from transform.utils import write_images


def create_sample_images():
    # Generate a list of simple images for testing
    images = []
    for color in [(255, 0, 0), (0, 255, 0), (0, 0, 255)]:  # Red, Green, Blue images
        img = Image.new("RGB", (10, 10), color)
        images.append(img)
    return images


def test_write_images_multiple_images():
    images = create_sample_images()
    with tempfile.NamedTemporaryFile(suffix=".tar.gz") as temp_file_multi:
        write_images(images, temp_file_multi.name)
        # Check that the output is a tar.gz file
        assert tarfile.is_tarfile(temp_file_multi.name)
        # Verify the contents of the tar archive
        with tarfile.open(temp_file_multi.name, "r:gz") as tar:
            members = tar.getmembers()
            assert len(members) == len(images)
            for i, member in enumerate(members):
                assert member.name == f"{str(i).zfill(4)}.png"


def test_write_images_single_image():
    images = create_sample_images()
    single_image = images[:1]  # Just one image
    with tempfile.NamedTemporaryFile(suffix=".png") as temp_file_single:
        write_images(single_image, temp_file_single.name)
        # Check that the output is a single file, not a tar.gz
        assert os.path.isfile(temp_file_single.name)
        assert not tarfile.is_tarfile(temp_file_single.name)


def test_write_images_custom_extension():
    images = create_sample_images()
    with tempfile.NamedTemporaryFile(suffix=".jpg") as temp_file_custom:
        output_tar_path = f"{temp_file_custom.name}.tar.gz"
        write_images(images, temp_file_custom.name, ext="jpg")
        # Check that the output is a tar.gz with .jpg images inside
        assert tarfile.is_tarfile(output_tar_path)
        # Verify the contents of the tar archive
        with tarfile.open(output_tar_path, "r:gz") as tar:
            members = tar.getmembers()
            assert len(members) == len(images)
            for i, member in enumerate(members):
                assert member.name == f"{str(i).zfill(4)}.jpg"
        # Clean up the output tar.gz file
        os.remove(output_tar_path)


def test_write_images_output_file_naming():
    images = create_sample_images()
    with tempfile.NamedTemporaryFile(suffix=".output") as temp_file_naming:
        write_images(images, temp_file_naming.name)
        # Check that the output file name is appended with .tar.gz if needed
        expected_output = f"{temp_file_naming.name}.tar.gz"
        assert os.path.isfile(expected_output)
        assert tarfile.is_tarfile(expected_output)
