import mimetypes
import os
import shutil
import tempfile

from pyramid.response import FileResponse

from tests.resources import TRANSFORM_PATH
from weaver.transform.transform import CONVERSION_DICT, Transform


def using_mimes(func):
    def wrapper(*args, **kwargs):
        cmt = mimetypes.guess_type(args[0])[0]
        if cmt in CONVERSION_DICT:
            for wmt in CONVERSION_DICT[cmt]:
                func(args[0], cmt, wmt)

    return wrapper


@using_mimes
def transform(f, cmt="", wmt=""):
    try:
        with tempfile.TemporaryDirectory() as tmp_path:
            shutil.copy(f, os.path.join(tmp_path, os.path.basename(f)))
            f = os.path.join(tmp_path, os.path.basename(f))
            trans = Transform(file_path=f, current_media_type=cmt, wanted_media_type=wmt)
            assert isinstance(trans.get(), FileResponse), f"{cmt} -> {wmt}"
            print(f"{cmt} -> {wmt} passed")
            return trans.output_path
    except Exception as err:
        print(f"{cmt} -> {wmt} failed")
        assert False, f"{os.path.splitext(f)[1]} -> {f} {str(err)}"


def test_transformations():
    for file_name in os.listdir(TRANSFORM_PATH):
        transform(os.path.join(TRANSFORM_PATH, file_name))
