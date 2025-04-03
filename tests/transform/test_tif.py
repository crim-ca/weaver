from unittest.mock import MagicMock, patch

import numpy as np
from PIL import Image

from weaver.transform.tiff import Tiff, normalize_band


@patch("rasterio.open", autospec=True)
@patch("multipagetiff.read_stack", autospec=True)
def test_tiff_init(mock_read_stack, mock_rasterio_open):
    mock_dataset = MagicMock()
    mock_dataset.crs = None  # Ensure it is NOT a GeoTIFF
    mock_rasterio_open.return_value = mock_dataset

    dummy_stack = np.random.randint(0, 255, (2, 2, 3), dtype=np.uint8)
    mock_read_stack.return_value = dummy_stack

    tiff = Tiff("dummy.tiff")

    assert tiff.file_path == "dummy.tiff"
    assert tiff.is_geotiff is False, f"Expected False but got {tiff.is_geotiff}"
    assert isinstance(tiff.images, np.ndarray)
    assert tiff.images.shape == (2, 2, 3)


def test_normalize_band():
    image_band = np.array([[10, 20], [30, 40]], dtype=np.float32)
    normalized = normalize_band(image_band)
    assert normalized.min() == 0.0
    assert normalized.max() == 1.0
    assert np.allclose(normalized, np.array([[0.0, 0.3333], [0.6667, 1.0]], dtype=np.float32), atol=1e-4)


@patch("rasterio.open", autospec=True)
@patch("multipagetiff.read_stack", autospec=True)
def test_get_images_non_geotiff(mock_read_stack, mock_rasterio_open):
    mock_dataset = MagicMock()
    mock_dataset.crs = None  # Ensure it is NOT a GeoTIFF
    mock_rasterio_open.return_value = mock_dataset

    dummy_stack = np.random.randint(0, 255, (2, 2, 3, 2), dtype=np.uint8)

    mock_images = MagicMock()
    mock_images.pages = dummy_stack

    mock_read_stack.return_value = mock_images

    tiff = Tiff("dummy_multipage.tiff")
    images = tiff.get_images()

    assert len(images) == 2, f"Expected 2 images but got {len(images)}"
    assert isinstance(images[0], Image.Image), "First item is not an Image object"
    assert images[0].size == (3, 2), f"First image size is not (3, 2): {images[0].size}"
    assert images[1].size == (3, 2), f"Second image size is not (3, 2): {images[1].size}"


@patch("rasterio.open")
def test_tiff_geotiff(mock_rasterio_open):
    mock_dataset = MagicMock()
    mock_dataset.crs = "EPSG:4326"
    mock_dataset.count = 3
    mock_dataset.width = 100
    mock_dataset.height = 100
    mock_dataset.indexes = [1, 2, 3]
    mock_dataset.dtypes = ["uint8", "uint8", "uint8"]
    mock_dataset.transform.__mul__.side_effect = lambda x: (x, x)
    mock_rasterio_open.return_value = mock_dataset

    tiff = Tiff("dummy_geotiff.tif")
    assert tiff.is_geotiff is True
    assert tiff.nb_bands == 3
    assert tiff.width == 100
    assert tiff.height == 100
    assert tiff.bands == {1: "uint8", 2: "uint8", 3: "uint8"}


@patch("rasterio.open")
def test_get_band(mock_rasterio_open):
    mock_dataset = MagicMock()
    mock_dataset.count = 3
    mock_dataset.read.return_value = np.array([[1, 2], [3, 4]])
    mock_rasterio_open.return_value = mock_dataset

    tiff = Tiff("dummy.tiff")
    band = tiff.get_band(1)
    assert band is not None
    assert band.shape == (2, 2)
    assert (band == np.array([[1, 2], [3, 4]])).all()


@patch("rasterio.open")
def test_get_images(mock_rasterio_open):
    mock_dataset = MagicMock()
    mock_dataset.count = 3
    mock_dataset.read.side_effect = [np.ones((2, 2)), np.ones((2, 2)) * 2, np.ones((2, 2)) * 3]
    mock_rasterio_open.return_value = mock_dataset

    tiff = Tiff("dummy.tiff")
    images = tiff.get_images()
    assert isinstance(images, list)
    assert isinstance(images[0], Image.Image)
    assert images[0].size == (2, 2)
