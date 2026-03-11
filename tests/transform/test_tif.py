import os

import numpy as np
from PIL import Image

from weaver.transform.tiff import Tiff, normalize_band

TEST_RESOURCES = os.path.join(os.path.dirname(__file__), "..", "resources", "transform")
MULTI_TIF_PATH = os.path.join(TEST_RESOURCES, "multi.tif")
DUBAI_TIF_PATH = os.path.join(TEST_RESOURCES, "dubai.tif")
WILDFIRES_TIF_PATH = os.path.join(TEST_RESOURCES, "wildfires.tif")


def test_tiff_init():
    """
    Test initialization with a TIFF file.
    """
    tiff = Tiff(WILDFIRES_TIF_PATH)

    assert tiff.file_path == WILDFIRES_TIF_PATH
    assert tiff.dataset is not None
    # Check that initialization sets is_geotiff appropriately
    assert isinstance(tiff.is_geotiff, bool)


def test_normalize_band():
    """
    Test band normalization to [0, 1] range.
    """
    image_band = np.array([[10, 20], [30, 40]], dtype=np.float32)
    normalized = normalize_band(image_band)
    assert normalized.min() == 0.0
    assert normalized.max() == 1.0
    assert np.allclose(normalized, np.array([[0.0, 0.3333], [0.6667, 1.0]], dtype=np.float32), atol=1e-4)


def test_get_images_multi_tif():
    """
    Test getting images from a multi-page or regular TIFF file.
    """
    tiff = Tiff(MULTI_TIF_PATH)
    images = tiff.get_images()

    assert isinstance(images, list), "Expected a list of images"
    assert len(images) > 0, f"Expected at least 1 image but got {len(images)}"
    assert isinstance(images[0], Image.Image), "First item is not an Image object"
    # Verify all items are PIL Images
    for idx, img in enumerate(images):
        assert isinstance(img, Image.Image), f"Image at index {idx} is not an Image object"


def test_get_images_dubai_tif():
    """
    Test getting images from dubai.tif.
    """
    tiff = Tiff(DUBAI_TIF_PATH)
    images = tiff.get_images()

    assert isinstance(images, list), "Expected a list of images"
    assert len(images) > 0, f"Expected at least 1 image but got {len(images)}"
    assert isinstance(images[0], Image.Image), "First item is not an Image object"


def test_tiff_geotiff():
    """
    Test initialization and properties of a GeoTIFF file.
    """
    tiff = Tiff(WILDFIRES_TIF_PATH)
    assert tiff.is_geotiff is True
    assert tiff.nb_bands > 0
    assert tiff.width > 0
    assert tiff.height > 0
    assert len(tiff.bands) == tiff.nb_bands
    assert tiff.crs is not None


def test_get_band():
    """
    Test getting a specific band from a GeoTIFF.
    """
    tiff = Tiff(WILDFIRES_TIF_PATH)
    band = tiff.get_band(1)
    assert band is not None
    assert isinstance(band, np.ndarray)
    assert band.shape == (tiff.height, tiff.width)

    # Test invalid band
    invalid_band = tiff.get_band(tiff.nb_bands + 10)
    assert invalid_band is None


def test_get_images_geotiff():
    """
    Test getting RGB images from a GeoTIFF.
    """
    tiff = Tiff(WILDFIRES_TIF_PATH)
    images = tiff.get_images()
    assert isinstance(images, list)
    assert len(images) == 1, "GeoTIFF should return a single combined image"
    assert isinstance(images[0], Image.Image)
    assert images[0].size == (tiff.width, tiff.height)


def test_multipage_detection():
    """
    Test that multi-page TIFFs are properly detected and loaded.
    """
    # Test with multi.tif - could be GeoTIFF or multi-page
    tiff_multi = Tiff(MULTI_TIF_PATH)

    # Verify basic attributes exist
    assert hasattr(tiff_multi, 'is_geotiff'), "Missing is_geotiff attribute"
    assert hasattr(tiff_multi, 'file_path'), "Missing file_path attribute"
    assert hasattr(tiff_multi, 'dataset'), "Missing dataset attribute"

    if not tiff_multi.is_geotiff:
        # If it's detected as non-GeoTIFF, it should have images attribute with pages
        assert hasattr(tiff_multi, 'images'), "Non-GeoTIFF should have 'images' attribute"
        assert hasattr(tiff_multi.images, 'pages'), "Images object should have 'pages' attribute"
    else:
        # If it's a GeoTIFF, it should have band-related attributes
        assert hasattr(tiff_multi, 'nb_bands'), "GeoTIFF should have 'nb_bands' attribute"
        assert hasattr(tiff_multi, 'crs'), "GeoTIFF should have 'crs' attribute"
        assert tiff_multi.nb_bands > 0, "GeoTIFF should have at least 1 band"

    # Either way, get_images should work
    images = tiff_multi.get_images()
    assert isinstance(images, list), "get_images should return a list"
    assert len(images) > 0, "get_images should return at least one image"
