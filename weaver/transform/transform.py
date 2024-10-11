import base64
import csv
import json
import os.path
import shutil
import tarfile
import tempfile

from markupsafe import escape
import pandas as pd
import xmltodict
import yaml
from bs4 import BeautifulSoup
from cairosvg import svg2png
from celery.utils.log import get_task_logger
from fpdf import FPDF
from json2xml import json2xml
from json2xml.utils import readfromjson
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
def image_to_any(i, o):
    # exit if no transformation needed
    if os.path.splitext(i)[1] == os.path.splitext(o)[1]:
        if not os.path.exists(o):
            shutil.copy(i, o)
        return

    if is_tiff(i):
        tif = Tiff(i)
        return images_to_any(tif.get_images(), o)

    if is_gif(i):
        return images_to_any([Image.open(i).convert('RGB')], o)

    if is_svg(i):
        png = f"{i}.png"
        svg2png(open(i, 'rb').read(), write_to=open(png, 'wb'))
        i = png

    return images_to_any([Image.open(i)], o)


def images_to_any(ims, o):
    ret = []
    with tempfile.TemporaryDirectory() as tmp_path:
        _o = os.path.join(tmp_path, str(len(ret)).zfill(4) + get_file_extension(o))
        for im in ims:
            clrs = im.getpixel((0, 0))
            if not isinstance(clrs, tuple):
                im = im.convert('RGB')
                clrs = im.getpixel((0, 0))
            if is_image(_o):
                if is_png(_o) and len(clrs) == 3:
                    im.putalpha(0)
                    im.save(_o)

                if not is_png(_o) and len(clrs) == 4:
                    im.load()
                    bg = Image.new("RGB", im.size, (255, 255, 255))
                    bg.paste(im, mask=im.split()[3])
                    bg.save(_o)
                else:
                    im.save(_o)

            elif is_svg(_o):
                width, height = im.size
                basewidth = 300
                if max(width, height) > basewidth:
                    wpercent = basewidth / float(im.size[0])
                    hsize = int((float(im.size[1]) * float(wpercent)))
                    im = im.resize((basewidth, hsize), Image.Resampling.LANCZOS)
                if len(clrs) == 3:
                    im.putalpha(0)

                write_content(_o, rgba_image_to_svg_contiguous(im))
            ret.append(_o)

        if len(ret) == 1:
            shutil.copy(ret[0], o)
        else:
            if not o.endswith(".tar.gz"):
                o += ".tar.gz"

            with tarfile.open(o, "w:gz") as tar:
                for fn in ret:
                    p = os.path.join(tmp_path, fn)
                    tar.add(p, arcname=fn)


@exception_handler
def any_to_html(i, o):
    try:
        if not is_image(i):
            content = get_content(i)
            # Escape and replace content in HTML
            html_content = HTML_CONTENT.replace("%CONTENT%", escape(content))  # Use escape from markupsafe
            write_content(o, html_content)
        else:
            jpg = f"{i}.jpg"
            image_to_any(i, jpg)
            with open(jpg, "rb") as img_file:
                img_data = base64.b64encode(img_file.read()).decode("utf-8")  # Base64 encode the image content
            write_content(o, HTML_CONTENT.replace("%CONTENT%", f'<img src="data:image/jpeg;base64,{img_data}" alt="Result" />'))
    except Exception as e:
        print(f"An error occurred: {str(e)}")  # Print the error message
        raise RuntimeError(f"Error processing file {i}: {str(e)}")



@exception_handler
def any_to_pdf(i, o):
    image = Image.open(i) if is_image(i) else None
    new_pdf = FPDF(orientation='P', unit='pt', format='A4')
    if image is None:
        # If input is not an image, treat it as text
        new_pdf.add_page()
        new_pdf.set_font("Arial", size=12)
        new_pdf.multi_cell(0, 10, txt=get_content(i), align='L')
    else:
        if is_tiff(i):
            tiff = Tiff(i)
            ims = tiff.get_images()  # For TIFF files with multiple pages
        else:
            ims = [image.convert('RGB')]

        new_pdf.set_margins(10, 10)

        pdf_width = new_pdf.w - 20
        pdf_height = new_pdf.h - 20

        for im in ims:
            image_w, image_h = im.size

            if image_w > image_h:
                new_pdf.add_page(orientation='L')
                _w, _h = pdf_height, pdf_width
            else:
                new_pdf.add_page(orientation='P')
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
            im.save(im_path)  # Save image to temp path for FPDF
            new_pdf.image(im_path, x=x_offset, y=y_offset, w=image_w, h=image_h)

    new_pdf.output(o, 'F')


@exception_handler
def csv_to_json(i, o):
    with open(i, encoding='utf-8') as csvf:
        csvReader = csv.DictReader(csvf)

        for i in range(len(csvReader.fieldnames)):
            if csvReader.fieldnames[i] == "":
                csvReader.fieldnames[i] = f"unknown_{str(i)}"

        ret = []
        for rows in csvReader:
            ret.append({"data": rows})
        # datas = {"datas": ret}
        write_content(o, {"datas": ret})


@exception_handler
def csv_to_xml(i, o):
    p = f"{i}.json"
    csv_to_json(i, p)
    data = readfromjson(p)
    write_content(o, json2xml.Json2xml(data, item_wrap=False).to_xml())


@exception_handler
def json_to_xml(i, o):
    data = readfromjson(i)
    write_content(o, json2xml.Json2xml(data, item_wrap=False).to_xml())


@exception_handler
def json_to_yaml(i, o):
    with open(i, 'r') as file:
        configuration = json.load(file)
    with open(o, 'w') as yaml_file:
        yaml.dump(configuration, yaml_file)


@exception_handler
def yaml_to_json(i, o):
    with open(i, 'r') as file:
        configuration = yaml.safe_load(file)
    with open(o, 'w') as json_file:
        json.dump(configuration, json_file)


@exception_handler
def json_to_csv(i, o):
    with open(i, encoding='utf-8') as inputfile:
        df = pd.read_json(inputfile)
        df.to_csv(o, encoding='utf-8', index=False)


@exception_handler
def xml_to_json(i, o):
    write_content(o, xmltodict.parse(get_content(i)))


@exception_handler
def html_to_txt(i, o):
    write_content(o, ' '.join(BeautifulSoup(get_content(i), "html.parser").stripped_strings))


@exception_handler
def yaml_to_csv(i, o):
    yaml_to_json(i, f"{i}.json")
    json_to_csv(f"{i}.json", o)


@exception_handler
def yaml_to_xml(i, o):
    yaml_to_json(i, f"{i}.json")
    json_to_xml(f"{i}.json", o)


@exception_handler
def xml_to_yaml(i, o):
    xml_to_json(i, f"{i}.json")
    json_to_yaml(f"{i}.json", o)


@exception_handler
def csv_to_yaml(i, o):
    csv_to_json(i, f"{i}.json")
    json_to_yaml(f"{i}.json", o)


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
                    # Plain
                    if "plain" in self.cmt:
                        # to HTML
                        if "html" in self.wmt:
                            any_to_html(self.file_path, self.output_path)
                        # to PDF
                        if "pdf" in self.wmt:
                            any_to_pdf(self.file_path, self.output_path)
                    # HTML
                    if "html" in self.cmt:
                        # to Plain
                        if "plain" in self.wmt:
                            html_to_txt(self.file_path, self.output_path)
                    # CSV
                    if "csv" in self.cmt:
                        # to JSON
                        if "json" in self.wmt:
                            csv_to_json(self.file_path, self.output_path)
                        # to XML
                        if "xml" in self.wmt:
                            csv_to_xml(self.file_path, self.output_path)
                        # to YAML
                        if "yaml" in self.wmt:
                            csv_to_yaml(self.file_path, self.output_path)
                elif "application/" in self.cmt:

                    # JSON
                    if "json" in self.cmt:
                        # to CSV
                        if "csv" in self.wmt:
                            json_to_csv(self.file_path, self.output_path)
                        # to XML
                        if "xml" in self.wmt:
                            json_to_xml(self.file_path, self.output_path)
                        # to YAML
                        if "yaml" in self.wmt:
                            json_to_xml(self.file_path, self.output_path)

                    # YAML
                    if "yaml" in self.cmt:
                        # to CSV
                        if "csv" in self.wmt:
                            yaml_to_csv(self.file_path, self.output_path)
                        # to JSON
                        if "json" in self.wmt:
                            yaml_to_json(self.file_path, self.output_path)
                        # to XML
                        if "xml" in self.wmt:
                            yaml_to_xml(self.file_path, self.output_path)
                    # XML
                    if "xml" in self.cmt:
                        # to JSON
                        if "json" in self.wmt:
                            xml_to_json(self.file_path, self.output_path)
                        # to YAML
                        if "yaml" in self.wmt:
                            xml_to_yaml(self.file_path, self.output_path)
                elif "image/" in self.cmt:
                    # Potential conversion
                    if "image/" in self.wmt:
                        image_to_any(self.file_path, self.output_path)
                        if not os.path.exists(self.output_path) and os.path.exists(f"{self.output_path}.tar.gz"):
                            self.output_path += ".tar.gz"
                    # PDF conversion
                    if "pdf" in self.wmt:
                        any_to_pdf(self.file_path, self.output_path)
        except Exception:
            raise

    def get(self):
        # type:(...) -> FileResponse
        try:
            if not os.path.exists(self.output_path):
                self.process()
            response = FileResponse(self.output_path)
            response.headers['Content-Disposition'] = f"attachment;  filename={os.path.basename(self.output_path)}"
            return response
        except Exception as e:
            raise HTTPUnprocessableEntity(json={
                "code": "JobOutputProcessingError",
                "description": "An error occured while treating the output data",
                "cause": str(e),
                "error": type(e).__name__,
                "value": ""
            })

