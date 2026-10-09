import os
import shutil
import tempfile
import zipfile

import pytest
from pyramid.httpexceptions import HTTPUnprocessableEntity
from pyramid.response import FileResponse

from tests.resources import TRANSFORM_PATH
from weaver.formats import ContentType, get_content_type
from weaver.transform.const import CONVERSION_DICT
from weaver.transform.handlers import Transform
from weaver.transform.utils import extend_alternate_formats


def using_mimes(func):
    def wrapper(*args, **kwargs):
        ext = os.path.splitext(args[0])[1]
        cmt = get_content_type(ext)
        if cmt and cmt in CONVERSION_DICT:
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


@pytest.mark.parametrize("file_ext,content,current_type,wanted_type", [
    ("csv", "col1,col2\nval1,val2\n", ContentType.TEXT_CSV, ContentType.APP_PDF),
    ("json", '{"key": "value"}', ContentType.APP_JSON, ContentType.IMAGE_PNG),
    ("yaml", "key: value\n", ContentType.APP_X_YAML, ContentType.IMAGE_PNG),
    ("xml", "<root><item>value</item></root>", ContentType.APP_XML, ContentType.TEXT_CSV),
])
def test_unsupported_conversions(file_ext, content, current_type, wanted_type):
    with tempfile.TemporaryDirectory() as tmp_path:
        test_file = os.path.join(tmp_path, f"test.{file_ext}")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(content)

        trans = Transform(file_path=test_file, current_media_type=current_type, wanted_media_type=wanted_type)
        with pytest.raises(HTTPUnprocessableEntity):
            trans.get()


def test_unsupported_image_conversion():
    from PIL import Image
    with tempfile.TemporaryDirectory() as tmp_path:
        png_file = os.path.join(tmp_path, "test.png")
        img = Image.new('RGB', (100, 100), color='red')
        img.save(png_file)

        trans = Transform(
            file_path=png_file,
            current_media_type=ContentType.IMAGE_PNG,
            wanted_media_type=ContentType.TEXT_CSV
        )
        with pytest.raises(HTTPUnprocessableEntity):
            trans.get()


def test_transform_same_media_type():
    with tempfile.TemporaryDirectory() as tmp_path:
        txt_file = os.path.join(tmp_path, "test.txt")
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write("test content")

        trans = Transform(
            file_path=txt_file,
            current_media_type=ContentType.TEXT_PLAIN,
            wanted_media_type=ContentType.TEXT_PLAIN
        )
        result = trans.get()
        assert isinstance(result, FileResponse)
        assert trans.output_path == txt_file


@pytest.mark.parametrize("file_ext,content,current_type,wanted_type,expected_ext", [
    ("txt", "test content", ContentType.TEXT_PLAIN, ContentType.TEXT_HTML, ".html"),
    ("txt", "test content for PDF", ContentType.TEXT_PLAIN, ContentType.APP_PDF, ".pdf"),
    ("html", "<html><body><p>test content</p></body></html>", ContentType.TEXT_HTML, ContentType.TEXT_PLAIN, ".txt"),
    ("json", '{"key": "value", "number": 123}', ContentType.APP_JSON, ContentType.TEXT_PLAIN, ".txt"),
])
def test_successful_conversions(file_ext, content, current_type, wanted_type, expected_ext):
    with tempfile.TemporaryDirectory() as tmp_path:
        test_file = os.path.join(tmp_path, f"test.{file_ext}")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(content)

        trans = Transform(file_path=test_file, current_media_type=current_type, wanted_media_type=wanted_type)
        result = trans.get()
        assert isinstance(result, FileResponse)
        assert os.path.exists(trans.output_path)
        assert trans.output_path.endswith(expected_ext)


def test_output_file_already_exists():
    with tempfile.TemporaryDirectory() as tmp_path:
        json_file = os.path.join(tmp_path, "test.json")
        xml_file = os.path.join(tmp_path, "test.xml")

        with open(json_file, "w", encoding="utf-8") as f:
            f.write('{"key": "value"}')

        with open(xml_file, "w", encoding="utf-8") as f:
            f.write("<old>content</old>")

        trans = Transform(file_path=json_file, current_media_type=ContentType.APP_JSON,
                          wanted_media_type=ContentType.APP_XML)
        result = trans.get()
        assert isinstance(result, FileResponse)
        assert os.path.exists(trans.output_path)


def test_csv_with_empty_headers():
    with tempfile.TemporaryDirectory() as tmp_path:
        csv_file = os.path.join(tmp_path, "test.csv")
        with open(csv_file, "w", encoding="utf-8") as f:
            f.write(",col2,\nval1,val2,val3\n")

        trans = Transform(
            file_path=csv_file,
            current_media_type=ContentType.TEXT_CSV,
            wanted_media_type=ContentType.APP_JSON
        )
        result = trans.get()
        assert isinstance(result, FileResponse)
        assert os.path.exists(trans.output_path)


def _make_zarr_dir(parent):
    zarr_dir = os.path.join(parent, "data.zarr")
    os.makedirs(os.path.join(zarr_dir, "var", "c"))
    for rel_path, content in [
        ("zarr.json", '{"zarr_format": 3, "node_type": "group"}'),
        (os.path.join("var", "zarr.json"), '{"zarr_format": 3, "node_type": "array"}'),
        (os.path.join("var", "c", "0"), "chunk"),
    ]:
        with open(os.path.join(zarr_dir, rel_path), "w", encoding="utf-8") as f:
            f.write(content)
    return zarr_dir


@pytest.mark.parametrize("zarr_type", sorted(ContentType.ANY_ZARR))
def test_zarr_directory_to_zip(zarr_type):
    with tempfile.TemporaryDirectory() as tmp_path:
        zarr_dir = _make_zarr_dir(tmp_path)

        # directories are provided with trailing slash from resolved result locations
        trans = Transform(
            file_path=f"{zarr_dir}/",
            current_media_type=zarr_type,
            wanted_media_type=ContentType.APP_ZARR_ZIP,
        )
        assert isinstance(trans.get(), FileResponse)
        assert trans.output_path == f"{zarr_dir}.zip"
        assert trans.output_path.endswith(".zarr.zip")

        with zipfile.ZipFile(trans.output_path) as zip_file:
            # store contents must be at the archive root, not nested under the directory name
            assert sorted(zip_file.namelist()) == ["var/c/0", "var/zarr.json", "zarr.json"]
            assert all(info.compress_type == zipfile.ZIP_STORED for info in zip_file.infolist())
            assert zip_file.read("var/c/0") == b"chunk"


def test_zarr_directory_unsupported_conversion():
    with tempfile.TemporaryDirectory() as tmp_path:
        zarr_dir = _make_zarr_dir(tmp_path)
        trans = Transform(
            file_path=f"{zarr_dir}/",
            current_media_type=ContentType.APP_ZARR,
            wanted_media_type=ContentType.APP_PDF,
        )
        with pytest.raises(HTTPUnprocessableEntity):
            trans.get()


@pytest.mark.parametrize("zarr_type", sorted(ContentType.ANY_ZARR))
def test_extend_alternate_formats_zarr(zarr_type):
    formats = [{"mediaType": zarr_type}]
    extended = extend_alternate_formats(formats)
    assert [fmt["mediaType"] for fmt in extended] == [zarr_type, ContentType.APP_ZARR_ZIP]


def test_extend_alternate_formats_zarr_parameter_spelling():
    zarr_type = f"{ContentType.APP_ZARR};version=3"  # not exactly the same string as the predefined version variant
    extended = extend_alternate_formats([{"mediaType": zarr_type}])
    assert [fmt["mediaType"] for fmt in extended] == [zarr_type, ContentType.APP_ZARR_ZIP]


def test_extend_alternate_formats_zarr_no_duplicates():
    formats = [{"mediaType": ContentType.APP_ZARR_V2}, {"mediaType": ContentType.APP_ZARR_V3}]
    extended = extend_alternate_formats(formats)
    assert [fmt["mediaType"] for fmt in extended] == [
        ContentType.APP_ZARR_V2,
        ContentType.APP_ZARR_V3,
        ContentType.APP_ZARR_ZIP,
    ]


@pytest.mark.parametrize("media_type", [ContentType.APP_ZARR_ZIP, ContentType.APP_ZIP])
def test_extend_alternate_formats_zip_not_zarr(media_type):
    """
    Zipped files, zarr or not, are not offered as Zarr directory (file cannot be returned as a directory).
    """
    formats = [{"mediaType": media_type}]
    assert extend_alternate_formats(formats) == formats
