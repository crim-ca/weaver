import multipagetiff as mtif
import numpy as np
import rasterio
from PIL import Image, UnidentifiedImageError

from weaver.transform.utils import write_images


def normalize_band(image_band: np.ndarray) -> np.ndarray:
    band_min, band_max = image_band.min(), image_band.max()  # type: ignore  # IDE type stub error
    return (image_band - band_min) / (band_max - band_min)


def brighten_band(image_band: np.ndarray, alpha: float = 0.13, beta: float = 0.0,
                  gamma: float = 2.0) -> np.ndarray:
    return np.clip(np.power(alpha * image_band + beta, 1. / gamma), 0, 255)


class Tiff:
    def __init__(self, file_path):
        self.fp = file_path
        self.dataset = rasterio.open(self.fp)

        self.is_geotiff = self.dataset.crs is not None

        if not self.is_geotiff:
            try:
                self.images = mtif.read_stack(self.fp)
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
    def range(self):
        return range(1, self.nb_bands + 1)

    def get_band(self, index):
        try:
            if index in self.range:
                return self.dataset.read(index)
            return None
        except:
            raise

    def get_images(self, red_band: int = 1, green_band: int = 2, blue_band: int = 3):
        if self.is_geotiff:
            indexes = [i for i in [red_band, green_band, blue_band] if i in self.range]
            array = (
                    np.dstack([
                        normalize_band(self.get_band(idx)) for idx in indexes
                    ])
                    * 255
            ).astype(np.uint8)
            if len(indexes) < 3:
                array = np.squeeze(array, axis=2)

            return [Image.fromarray(array)]
        else:
            imlist = []
            for m in self.images.pages:
                imlist.append(Image.fromarray(m))
            return imlist

    def convert_to_png(self, output_file, red: int = 1, green: int = 2, blue: int = 3):
        write_images(self.get_images(red, green, blue), output_file, ext="png")
