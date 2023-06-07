import os
import shutil
import tempfile
import unittest

from pyramid.response import FileResponse

from tests import resources
from weaver.tranform.transform import Transform
from weaver.tranform.utils import get_file_extension


def transform(i, f, p="image"):
    try:
        ext = get_file_extension(i, False)
        if ext == "txt": ext = "plain"
        t = Transform(file_path=i, current_media_type=p + "/" + ext,
                      wanted_media_type=p + "/" + f)
        assert isinstance(t.get(), FileResponse), ext + " -> " + f + " " + str(t["error"])
        print(os.path.splitext(i)[1] + " -> " + f + " passed")
        return t.output_path
    except Exception as e:
        print(os.path.splitext(i)[1] + " -> " + f + " failed")
        assert False, os.path.splitext(i)[1] + " -> " + f + " " + str(e)
        pass


class TestTranform(unittest.TestCase):

    def run(self, f, exts, p="application"):
        with tempfile.TemporaryDirectory() as dirpath:
            dts = os.path.join(dirpath, os.path.basename(f))
            shutil.copy(f, dts)
            fs = []
            # fisrt convert infile to required format
            for ext in exts:
                fs.append(transform(dts, ext, p=p))

            # then convert all result files to all format
            for f in fs:
                if f.lower().endswith(".pdf"): continue  # No pdf conversion for now
                if f.lower().endswith(".xml"): continue  # No xml conversion for now, should fefine parser
                if f.lower().endswith(".html"): continue  # No html conversion for now
                for ext in exts:
                    transform(f, ext, p=p)

    def test_transformations(self):
        image = resources.WPS_TRANFORM_IMAGE_RESSOURCE
        text = resources.WPS_TRANFORM_TEXT_RESSOURCE
        datas = resources.WPS_TRANFORM_DATAS_RESSOURCE

        print("############# TRANSFORMATION STARTING #############")
        self.run(image, ["jpeg", "jpg", "gif", "svg", "tiff", "tif", "bmp", "png", "pdf"], "image")
        print("############# IMAGES ALL PASSED #############")
        self.run(datas, ["json", "xml", "yaml", "csv"], "application")
        print("############# DATAS ALL PASSED #############")
        self.run(text, ["plain", "html", "pdf"], "text")
        print("############# PLAIN ALL PASSED #############")
        print("############# TRANSFORMATION FINISHED #############")


if __name__ == '__main__':
    unittest.main()
