import mimetypes
import os
import shutil
import tempfile

from pyramid.response import FileResponse
from weaver.tranform.transform import Transform, FAMILIES


def using_mimes(func):
    def wrapper(*args, **kwargs):
        cmt = mimetypes.guess_type(args[0])[0]
        for family in FAMILIES:
            if cmt in family:
                for wmt in [f for f in family if f != cmt]:
                    func(args[0], cmt, wmt)

    return wrapper


@using_mimes
def transform(f, cmt="", wmt=""):
    try:
        with tempfile.TemporaryDirectory() as tmp_path:
            shutil.copy(f, os.path.join(tmp_path, os.path.basename(f)))
            f = os.path.join(tmp_path, os.path.basename(f))

            t = Transform(file_path=f, current_media_type=cmt, wanted_media_type=wmt)

            assert isinstance(t.get(), FileResponse), cmt + " -> " + wmt + " " + str(t["error"])
            print(cmt + " -> " + wmt + " passed")
            return t.output_path
    except Exception as e:
        print(cmt + " -> " + wmt + " failed")
        assert False, os.path.splitext(f)[1] + " -> " + f + " " + str(e)
        pass


def test_transformations():
    for fn in os.listdir("./res/transform"):
        transform(os.path.join("./res/transform", fn))



test_transformations()