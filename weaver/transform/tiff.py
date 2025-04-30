from typing import List, Optional

import multipagetiff as mtif
import numpy as np
import rasterio
from PIL import Image, UnidentifiedImageError


def normalize_band(image_band: np.ndarray) -> np.ndarray:
    """
    Normalize a single band of an image to the range [0, 1].

    :param image_band: The image band to normalize.
    :type image_band: np.ndarray
    :return: The normalized image band.
    :rtype: np.ndarray
    """
    band_min, band_max = image_band.min(), image_band.max()  # type: ignore  # IDE type stub error
    return (image_band - band_min) / (band_max - band_min)


class Tiff:
    """
    A class for working with TIFF files, including GeoTIFFs and multi-page TIFFs.

    :ivar file_path: The file path to the TIFF image.
    :vartype file_path: str
    :ivar dataset: The rasterio dataset for GeoTIFFs.
    :vartype dataset: rasterio.Dataset
    :ivar is_geotiff: A flag indicating whether the image is a GeoTIFF.
    :vartype is_geotiff: bool
    :ivar images: The list of image arrays for multi-page TIFFs.
    :vartype images: List[np.ndarray]
    :ivar _images: A copy of the list of image arrays.
    :vartype _images: List[np.ndarray]
    :ivar nb_bands: The number of bands in the GeoTIFF.
    :vartype nb_bands: int
    :ivar width: The width of the image.
    :vartype width: int
    :ivar height: The height of the image.
    :vartype height: int
    :ivar bands: A dictionary of band indexes and their data types.
    :vartype bands: dict
    :ivar coordinates: The coordinates for the GeoTIFF.
    :vartype coordinates: Tuple[Tuple[float, float], Tuple[float, float]]
    :ivar crs: The coordinate reference system for the GeoTIFF.
    :vartype crs: rasterio.crs.CRS
    """

    def __init__(self, file_path: str):
        """
        Initialize the Tiff object with the given file path.

        :param file_path: The file path to the TIFF image.
        :type file_path: str
        """
        self.file_path = file_path
        self.dataset = rasterio.open(self.file_path)

        self.is_geotiff = self.dataset.crs is not None

        if not self.is_geotiff:
            try:
                self.images = mtif.read_stack(self.file_path)
                self._images = self.images.copy()
            except Exception as ex:
                if isinstance(ex, UnidentifiedImageError):
                    self.is_geotiff = True
                else:
                    raise

        if self.is_geotiff:
            self.nb_bands = self.dataset.count
            self.width = self.dataset.width
            self.height = self.dataset.height

            self.bands = {i: dtype for i, dtype in zip(self.dataset.indexes, self.dataset.dtypes)}
            self.coordinates = (self.dataset.transform * (0, 0), self.dataset.transform * (self.width, self.height))

            self.crs = self.dataset.crs

    @property
    def range(self) -> range:
        """
        Get the range of valid band indexes for the TIFF file.

        :return: A range object representing valid band indexes.
        :rtype: range
        """
        return range(1, self.nb_bands + 1)

    def get_band(self, index: int) -> Optional[np.ndarray]:
        """
        Retrieve a specific band of the image by index.

        :param index: The band index to retrieve.
        :type index: int
        :return: The band as a NumPy array, or None if not found.
        :rtype: Optional[np.ndarray]
        :raises RuntimeError: If the band index is invalid or data cannot be read.
        """
        if index in self.range:
            return self.dataset.read(index)
        return None

    def get_images(self, red_band: int = 1, green_band: int = 2, blue_band: int = 3) -> List[Image.Image]:
        """
        Retrieve RGB images by combining bands from a GeoTIFF or multi-page TIFF.

        :param red_band: The band index for the red channel.
        :type red_band: int
        :param green_band: The band index for the green channel.
        :type green_band: int
        :param blue_band: The band index for the blue channel.
        :type blue_band: int
        :return: A list of PIL Image objects representing the RGB image(s).
        :rtype: List[Image.Image]
        """
        if self.is_geotiff:
            indexes = [i for i in [red_band, green_band, blue_band] if i in self.range]
            array = (
                np.dstack([normalize_band(self.get_band(idx)) for idx in indexes])
                * 255
            ).astype(np.uint8)
            if len(indexes) < 3:
                array = np.squeeze(array, axis=2)

            return [Image.fromarray(array)]
        else:
            imlist = []
            for page in self.images.pages:
                imlist.append(Image.fromarray(page))
            return imlist
