import base64
import csv
import json
import os.path
import shutil
import tarfile
import tempfile

import pandas as pd
import xmltodict
import yaml
from bs4 import BeautifulSoup
from cairosvg import svg2png
from celery.utils.log import get_task_logger
from fpdf import FPDF
from json2xml import json2xml
from json2xml.utils import readfromjson
from markupsafe import escape
from PIL import Image
from pyramid.httpexceptions import HTTPUnprocessableEntity
from pyramid.response import FileResponse

from weaver.formats import get_extension
from weaver.transform.png2svg import rgba_image_to_svg_contiguous
from weaver.transform.tiff import Tiff
from weaver.transform.utils import (
    get_content,
    get_file_extension,
    is_gif,
    is_image,
    is_png,
    is_svg,
    is_tiff,
    write_content
)

LOGGER = get_task_logger(__name__)

HTML_CONTENT = """<html>
    <head></head>
    <body><p>%CONTENT%</p></body>
    </html>"""


FAMILIES = [
    ["text/plain", "text/html", "application/pdf"],
    ["image/png", "image/gif", "image/jpeg", "image/tiff", "image/svg+xml", "application/pdf"],
    ["text/csv", "application/xml", "application/x-yaml", "application/json"]
]


def exception_handler(func):
    def inner_function(*args, **kwargs):
        try:
            if "_to_" in func.__name__:
                LOGGER.debug(f"{func.__name__} operation: [%s] -> [%s]", os.path.basename(args[0]),
                             os.path.basename(args[1]))
            func(*args, **kwargs)
        except Exception:
            raise

    return inner_function


@exception_handler
def image_to_any(i, out):
    # exit if no transformation needed
    if os.path.splitext(i)[1] == os.path.splitext(out)[1]:
        if not os.path.exists(out):
            shutil.copy(i, out)
        return

    if is_tiff(i):
        tif = Tiff(i)
        return images_to_any(tif.get_images(), out)

    if is_gif(i):
        return images_to_any([Image.open(i).convert("RGB")], out)

    if is_svg(i):
        png = f"{i}.png"
        with open(i, "rb") as svg_file:
            svg_data = svg_file.read()
        with open(png, "wb") as png_file:
            svg2png(svg_data, write_to=png_file)
        i = png

    return images_to_any([Image.open(i)], out)


def images_to_any(ims, out):
    ret = []
    with tempfile.TemporaryDirectory() as tmp_path:
        _o = os.path.join(tmp_path, str(len(ret)).zfill(4) + get_file_extension(out))
        for img in ims:
            clrs = img.getpixel((0, 0))
            if not isinstance(clrs, tuple):
                img = img.convert("RGB")
                clrs = img.getpixel((0, 0))
            if is_image(_o):
                if is_png(_o) and len(clrs) == 3:
                    img.putalpha(0)
                    img.save(_o)

                if not is_png(_o) and len(clrs) == 4:
                    img.load()
                    rbg = Image.new("RGB", img.size, (255, 255, 255))
                    rbg.paste(img, mask=img.split()[3])
                    rbg.save(_o)
                else:
                    img.save(_o)

            elif is_svg(_o):
                width, height = img.size
                basewidth = 300
                if max(width, height) > basewidth:
                    wpercent = basewidth / float(img.size[0])
                    hsize = int((float(img.size[1]) * float(wpercent)))
                    img = img.resize((basewidth, hsize), Image.Resampling.LANCZOS)
                if len(clrs) == 3:
                    img.putalpha(0)

                write_content(_o, rgba_image_to_svg_contiguous(img))
            ret.append(_o)

        if len(ret) == 1:
            shutil.copy(ret[0], out)
        else:
            if not out.endswith(".tar.gz"):
                out += ".tar.gz"

            with tarfile.open(out, "w:gz") as tar:
                for file_name in ret:
                    path = os.path.join(tmp_path, file_name)
                    tar.add(path, arcname=file_name)


@exception_handler
def any_to_html(i, out):
    try:
        if not is_image(i):
            content = get_content(i)
            # Escape and replace content in HTML
            html_content = HTML_CONTENT.replace("%CONTENT%", escape(content))  # Use escape from markupsafe
            write_content(out, html_content)
        else:
            jpg = f"{i}.jpg"
            image_to_any(i, jpg)
            with open(jpg, "rb") as img_file:
                img_data = base64.b64encode(img_file.read()).decode("utf-8")  # Base64 encode the image content
            write_content(out, HTML_CONTENT.replace(
                "%CONTENT%", f"<img src=\"data:image/jpeg;base64,{img_data}\" alt=\"Result\" />"))
    except Exception as err:
        print(f"An error occurred: {str(err)}")  # Print the error message
        raise RuntimeError(f"Error processing file {i}: {str(err)}")


@exception_handler
def any_to_pdf(i, out):
    image = Image.open(i) if is_image(i) else None
    new_pdf = FPDF(orientation="P", unit="pt", format="A4")
    if image is None:
        # If input is not an image, treat it as text
        new_pdf.add_page()
        new_pdf.set_font("Arial", size=12)
        new_pdf.multi_cell(0, 10, txt=get_content(i), align="L")
    else:
        if is_tiff(i):
            tiff = Tiff(i)
            ims = tiff.get_images()  # For TIFF files with multiple pages
        else:
            ims = [image.convert("RGB")]

        new_pdf.set_margins(10, 10)

        pdf_width = new_pdf.w - 20
        pdf_height = new_pdf.h - 20

        for img in ims:
            image_w, image_h = img.size

            if image_w > image_h:
                new_pdf.add_page(orientation="L")
                _w, _h = pdf_height, pdf_width
            else:
                new_pdf.add_page(orientation="P")
                _w, _h = pdf_width, pdf_height

            # Scale image down to fit within the PDF page while keeping aspect ratio
            aspect_ratio = image_w / image_h
            if image_w > _w:
                image_w = _w
                image_h = image_w / aspect_ratio
            if image_h > _h:
                image_h = _h
                image_w = image_h * aspect_ratio

            # Center the image on the page
            x_offset = (_w - image_w) / 2
            y_offset = (_h - image_h) / 2

            # Add the image to the PDF
            im_path = os.path.join(tempfile.gettempdir(), "temp_image.jpg")
            img.save(im_path)  # Save image to temp path for FPDF
            new_pdf.image(im_path, x=x_offset, y=y_offset, w=image_w, h=image_h)

    new_pdf.output(out, "F")


@exception_handler
def csv_to_json(i, out):
    with open(i, encoding="utf-8") as csvf:
        csv_reader = csv.DictReader(csvf)

        for idx, fieldname in enumerate(csv_reader.fieldnames):
            if fieldname == "":
                csv_reader.fieldnames[idx] = f"unknown_{idx}"
        ret = []
        for rows in csv_reader:
            ret.append({"data": rows})
        write_content(out, {"datas": ret})


@exception_handler
def csv_to_xml(i, out):
    file = f"{i}.json"
    csv_to_json(i, file)
    data = readfromjson(file)
    write_content(out, json2xml.Json2xml(data, item_wrap=False).to_xml())


@exception_handler
def json_to_xml(i, out):
    data = readfromjson(i)
    write_content(out, json2xml.Json2xml(data, item_wrap=False).to_xml())


@exception_handler
def json_to_yaml(i, out):
    with open(i, "r", encoding="utf-8") as file:
        configuration = json.load(file)
    with open(out, "w", encoding="utf-8") as yaml_file:
        yaml.dump(configuration, yaml_file)


@exception_handler
def yaml_to_json(i, out):
    with open(i, "r", encoding="utf-8") as file:
        configuration = yaml.safe_load(file)
    with open(out, "w", encoding="utf-8") as json_file:
        json.dump(configuration, json_file)


@exception_handler
def json_to_csv(i, out):
    with open(i, encoding="utf-8") as file:
        data_file = pd.read_json(file, encoding="utf-8")
        data_file.to_csv(out, encoding="utf-8", index=False)


@exception_handler
def xml_to_json(i, out):
    write_content(out, xmltodict.parse(get_content(i)))


@exception_handler
def html_to_txt(i, out):
    write_content(out, " ".join(BeautifulSoup(get_content(i), "html.parser").stripped_strings))


@exception_handler
def yaml_to_csv(i, out):
    yaml_to_json(i, f"{i}.json")
    json_to_csv(f"{i}.json", out)


@exception_handler
def yaml_to_xml(i, out):
    yaml_to_json(i, f"{i}.json")
    json_to_xml(f"{i}.json", out)


@exception_handler
def xml_to_yaml(i, out):
    xml_to_json(i, f"{i}.json")
    json_to_yaml(f"{i}.json", out)


@exception_handler
def csv_to_yaml(i, out):
    csv_to_json(i, f"{i}.json")
    json_to_yaml(f"{i}.json", out)


class Transform:
    def __init__(self, file_path, current_media_type: str, wanted_media_type: str):
        self.file_path = file_path
        self.cmt = current_media_type.lower()
        self.wmt = wanted_media_type.lower()
        self.output_path = self.file_path

        self.ext = get_extension(self.wmt)

        if self.cmt != self.wmt:
            self.output_path = self.file_path + self.ext
            if os.path.exists(self.output_path):
                try:
                    os.remove(self.output_path)
                except OSError as exc:
                    LOGGER.warning("Failed to delete [%s]", os.path.basename(self.output_path), exc)

    def process(self):
        try:
            if self.output_path != self.file_path:
                if "text/" in self.cmt:
                    self.process_text()
                elif "application/" in self.cmt:
                    self.process_application()
                elif "image/" in self.cmt:
                    self.process_image()
        except Exception as e:
            raise RuntimeError(f"Error processing file {self.file_path}: {str(e)}")

    def process_text(self):
        if "plain" in self.cmt:
            if "html" in self.wmt:
                any_to_html(self.file_path, self.output_path)
            if "pdf" in self.wmt:
                any_to_pdf(self.file_path, self.output_path)
        if "html" in self.cmt:
            if "plain" in self.wmt:
                html_to_txt(self.file_path, self.output_path)
        if "csv" in self.cmt:
            self.process_csv()

    def process_csv(self):
        if "json" in self.wmt:
            csv_to_json(self.file_path, self.output_path)
        if "xml" in self.wmt:
            csv_to_xml(self.file_path, self.output_path)
        if "yaml" in self.wmt:
            csv_to_yaml(self.file_path, self.output_path)

    def process_application(self):
        if "json" in self.cmt:
            self.process_json()
        if "yaml" in self.cmt:
            self.process_yaml()
        if "xml" in self.cmt:
            self.process_xml()

    def process_json(self):
        if "csv" in self.wmt:
            json_to_csv(self.file_path, self.output_path)
        if "xml" in self.wmt:
            json_to_xml(self.file_path, self.output_path)
        if "yaml" in self.wmt:
            json_to_yaml(self.file_path, self.output_path)

    def process_yaml(self):
        if "csv" in self.wmt:
            yaml_to_csv(self.file_path, self.output_path)
        if "json" in self.wmt:
            yaml_to_json(self.file_path, self.output_path)
        if "xml" in self.wmt:
            yaml_to_xml(self.file_path, self.output_path)

    def process_xml(self):
        if "json" in self.wmt:
            xml_to_json(self.file_path, self.output_path)
        if "yaml" in self.wmt:
            xml_to_yaml(self.file_path, self.output_path)

    def process_image(self):
        if "image/" in self.wmt:
            image_to_any(self.file_path, self.output_path)
            if not os.path.exists(self.output_path) and os.path.exists(f"{self.output_path}.tar.gz"):
                self.output_path += ".tar.gz"
        if "pdf" in self.wmt:
            any_to_pdf(self.file_path, self.output_path)

    def get(self):
        # type:(...) -> FileResponse
        try:
            if not os.path.exists(self.output_path):
                self.process()
            response = FileResponse(self.output_path)
            response.headers["Content-Disposition"] = f"attachment;  filename={os.path.basename(self.output_path)}"
            return response
        except Exception as err:
            raise HTTPUnprocessableEntity(json={
                "code": "JobOutputProcessingError",
                "description": "An error occured while treating the output data",
                "cause": str(err),
                "error": type(err).__name__,
                "value": ""
            })
