import os
import shutil
import tempfile

import pytest
from pyramid.httpexceptions import HTTPUnprocessableEntity
from pyramid.response import FileResponse

from tests.resources import TRANSFORM_PATH
from weaver.formats import ContentType, get_content_type
from weaver.transform.const import CONVERSION_DICT
from weaver.transform.handlers import Transform


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
