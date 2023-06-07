import base64
import csv
import json
import os.path
import shutil

import jinja2
import pandas as pd
import xmltodict
import yaml
from PIL import Image
from bs4 import BeautifulSoup
from cairosvg import svg2png
from celery.utils.log import get_task_logger
from fpdf import FPDF
from json2xml import json2xml
from json2xml.utils import readfromjson
from pyramid.httpexceptions import HTTPUnprocessableEntity
from pyramid.response import FileResponse

from weaver.formats import get_extension
from weaver.tranform.png2svg import rgba_image_to_svg_contiguous

from weaver.tranform.utils import is_png, is_gif, is_svg, write_content, get_content, is_image

LOGGER = get_task_logger(__name__)

HTML_CONTENT = """<html>
    <head></head>
    <body><p>%CONTENT%</p></body>
    </html>"""


FAMILIES = [
    ["text/plain", "text/html", "application/pdf"],
    ["image/png", "image/gif", "image/jpeg", "image/tiff", "image/svg+xml", "application/pdf"],
    ["application/csv", "application/xml", "application/application/x-yaml", "application/json"]
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

    if is_gif(i):
        Image.open(i).convert('RGB').save(i + '.jpg')
        image_to_any(i + '.jpg', o)
        return

    if is_image(i) and is_image(o):
        im = Image.open(i)
        clrs = im.getpixel((0, 0))

        if is_png(o) and len(clrs) == 3:
            im.putalpha(0)
            im.save(o)
        elif not is_png(o) and len(clrs) == 4:
            im.load()
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.split()[3])
            bg.save(o)
        else:
            im.save(o)

    elif is_svg(i) and is_image(o):
        png = i + ".png"
        svg2png(open(i, 'rb').read(), write_to=open(png, 'wb'))
        if not is_png(o):
            image_to_any(png, o)
    elif is_svg(o) and is_image(i):
        if not is_png(i):
            png = i + ".png"
            im = Image.open(i)
            im.putalpha(0)
            im.save(png)
        else:
            png = i
        write_content(o, rgba_image_to_svg_contiguous(Image.open(png)))


@exception_handler
def any_to_html(i, o):
    if not is_image(i):
        write_content(o, HTML_CONTENT.replace("%CONTENT%", jinja2.escape(get_content(i))))
    else:
        jpg = i + ".jpg"
        image_to_any(i, jpg)
        write_content(o, HTML_CONTENT.replace("%CONTENT%", "<img src=\"data:image/jpeg;base64," + base64.b64encode(
            get_content(jpg, "rb")) + "\" alt=\"Result\" />"))


@exception_handler
def any_to_pdf(i, o):
    image = Image.open(i) if is_image(i) else None

    if image is None:
        pdf = FPDF(orientation='P', unit='mm', format='A4')
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=get_content(i), ln=1, align='L')
        pdf.output(o)
    else:
        im = image.convert('RGB')
        im.save(o, save_all=True, append_images=[im])


@exception_handler
def csv_to_json(i, o):
    with open(i, encoding='utf-8') as csvf:
        csvReader = csv.DictReader(csvf)

        for i in range(len(csvReader.fieldnames)):
            if csvReader.fieldnames[i] == "":
                csvReader.fieldnames[i] = "unknown_" + str(i)

        ret = []
        for rows in csvReader:
            ret.append({"data": rows})
        # datas = {"datas": ret}
        write_content(o, {"datas": ret})


@exception_handler
def csv_to_xml(i, o):
    p = i + ".json"
    csv_to_json(i, p)
    data = readfromjson(p)
    write_content(o, json2xml.Json2xml(data, item_wrap=False).to_xml())


@exception_handler
def json_to_xml(i, o):
    data = readfromjson(i)
    write_content(o, json2xml.Json2xml(data, item_wrap=False).to_xml())


@exception_handler
def json_to_yaml(i, o):
    with open(i, 'r') as file: configuration = json.load(file)
    with open(o, 'w') as yaml_file: yaml.dump(configuration, yaml_file)


@exception_handler
def yaml_to_json(i, o):
    with open(i, 'r') as file: configuration = yaml.safe_load(file)
    with open(o, 'w') as json_file: json.dump(configuration, json_file)


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
    yaml_to_json(i, i + ".json")
    json_to_csv(i + ".json", o)


@exception_handler
def yaml_to_xml(i, o):
    yaml_to_json(i, i + ".json")
    json_to_xml(i + ".json", o)


@exception_handler
def xml_to_yaml(i, o):
    xml_to_json(i, i + ".json")
    json_to_yaml(i + ".json", o)


@exception_handler
def csv_to_yaml(i, o):
    csv_to_json(i, i + ".json")
    json_to_yaml(i + ".json", o)


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
                ext = self.wmt
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

                elif "application/" in self.cmt:
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
                            xml_to_json(self.file_path, self.output_pathh)
                        # to YAML
                        if "yaml" in self.wmt:
                            xml_to_yaml(self.file_path, self.output_pathh)
                elif "image/" in self.cmt:
                    # Potential conversion
                    if "image/" in self.wmt:
                        image_to_any(self.file_path, self.output_path)
                    # PDF conversion
                    if "pdf" in self.wmt:
                        any_to_pdf(self.file_path, self.output_path)
        except Exception:
            raise

    def get(self):
        try:
            if not os.path.exists(self.output_path): self.process()
            response = FileResponse(self.output_path)
            response.headers['Content-Disposition'] = ('attachment;  filename=' + os.path.basename(self.output_path))
            return response
        except Exception as e:
            raise HTTPUnprocessableEntity(json={
                "code": "JobOutputProcessingError",
                "description": "An error occured while treating the output data",
                "cause": str(e),
                "error": type(e).__name__,
                "value": ""
            })

    # Used for tests
    def _get(self):
        try:
            if not os.path.exists(self.output_path): self.process()
            return os.path.exists(self.output_path)
        except:
            raise
