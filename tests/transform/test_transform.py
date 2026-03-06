import mimetypes
import os
import shutil
import tempfile

import pytest
from pyramid.response import FileResponse

from tests.resources import TRANSFORM_PATH
from weaver.transform.transform import CONVERSION_DICT, Transform

# Register the MIME type for .yaml files
mimetypes.add_type("application/x-yaml", ".yaml")


def using_mimes(func):
    def wrapper(*args, **kwargs):
        cmt = mimetypes.guess_type(args[0])[0]
        if cmt in CONVERSION_DICT:
            for wmt in CONVERSION_DICT[cmt]:
                func(args[0], cmt, wmt)

    return wrapper


@using_mimes
def transform(f, cmt="", wmt=""):
    with tempfile.TemporaryDirectory() as tmp_path:
        shutil.copy(f, os.path.join(tmp_path, os.path.basename(f)))
        f = os.path.join(tmp_path, os.path.basename(f))
        trans = Transform(file_path=f, current_media_type=cmt, wanted_media_type=wmt)
        assert isinstance(trans.get(), FileResponse), f"{cmt} -> {wmt}"
        print(f"{cmt} -> {wmt} passed")
        return trans.output_path


@pytest.mark.parametrize("file_name", [f for f in os.listdir(TRANSFORM_PATH)
                                       if os.path.isfile(os.path.join(TRANSFORM_PATH, f))])
def test_transformations(file_name):
    file_path = os.path.join(TRANSFORM_PATH, file_name)
    transform(file_path)
