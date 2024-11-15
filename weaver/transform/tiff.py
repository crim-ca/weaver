from typing import List, Optional

import multipagetiff as mtif
import numpy as np
import rasterio
from PIL import Image, UnidentifiedImageError

from weaver.transform.utils import write_images


def normalize_band(image_band: np.ndarray) -> np.ndarray:
    """
    Normalize a single band of an image to the range [0, 1].

    Args:
        image_band (np.ndarray): The image band to normalize.

    Returns:
        np.ndarray: The normalized image band.
    """
    band_min, band_max = image_band.min(), image_band.max()  # type: ignore  # IDE type stub error
    return (image_band - band_min) / (band_max - band_min)


def brighten_band(image_band: np.ndarray, alpha: float = 0.13, beta: float = 0.0,
                  gamma: float = 2.0) -> np.ndarray:
    """
    Apply a brightness adjustment to a single band of an image using a gamma correction.

    Args:
        image_band (np.ndarray): The image band to adjust.
        alpha (float): The scaling factor for the image band.
        beta (float): The offset added to the image band before applying the power.
        gamma (float): The gamma factor for correction.

    Returns:
        np.ndarray: The brightened image band.
    """
    return np.clip(np.power(alpha * image_band + beta, 1. / gamma), 0, 255)


class Tiff:
    """
    A class for working with TIFF files, including GeoTIFFs and multi-page TIFFs.

    Attributes:
        file_path (str): The file path to the TIFF image.
        dataset (rasterio.Dataset): The rasterio dataset for GeoTIFFs.
        is_geotiff (bool): A flag indicating whether the image is a GeoTIFF.
        images (List[np.ndarray]): The list of image arrays for multi-page TIFFs.
        _images (List[np.ndarray]): A copy of the list of image arrays.
        nb_bands (int): The number of bands in the GeoTIFF.
        width (int): The width of the image.
        height (int): The height of the image.
        bands (dict): A dictionary of band indexes and their data types.
        coordinates (Tuple[Tuple[float, float], Tuple[float, float]]): The coordinates for the GeoTIFF.
        crs (rasterio.crs.CRS): The coordinate reference system for the GeoTIFF.
    """

    def __init__(self, file_path: str):
        """
        Initialize the Tiff object with the given file path.

        Args:
            file_path (str): The file path to the TIFF image.
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

        Returns:
            range: A range object representing valid band indexes.
        """
        return range(1, self.nb_bands + 1)

    def get_band(self, index: int) -> Optional[np.ndarray]:
        """
        Retrieve a specific band of the image by index.

        Args:
            index (int): The band index to retrieve.

        Returns:
            Optional[np.ndarray]: The band as a NumPy array, or None if not found.

        Raises:
            RuntimeError: If the band index is invalid or data cannot be read.
        """
        try:
            if index in self.range:
                return self.dataset.read(index)
            return None
        except KeyError as err:
            raise RuntimeError(f"Failed to read data at index {index}") from err

    def get_images(self, red_band: int = 1, green_band: int = 2, blue_band: int = 3) -> List[Image.Image]:
        """
        Retrieve RGB images by combining bands from a GeoTIFF or multi-page TIFF.

        Args:
            red_band (int): The band index for the red channel.
            green_band (int): The band index for the green channel.
            blue_band (int): The band index for the blue channel.

        Returns:
            List[Image.Image]: A list of PIL Image objects representing the RGB image(s).
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

    def convert_to_png(self, output_file: str, red: int = 1, green: int = 2, blue: int = 3):
        """
        Convert the TIFF file to a PNG image.

        Args:
            output_file (str): The path to save the PNG file.
            red (int): The band index for the red channel.
            green (int): The band index for the green channel.
            blue (int): The band index for the blue channel.
        """
        write_images(self.get_images(red, green, blue), output_file, ext="png")
