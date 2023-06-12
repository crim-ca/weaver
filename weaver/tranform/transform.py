import base64
import csv
import json
import os.path
import shutil
import tarfile
import tempfile

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
from weaver.tranform.tiff import Tiff

from weaver.tranform.utils import is_png, is_gif, is_svg, write_content, get_content, is_image, is_tiff, \
    get_file_extension

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
        png = i + ".png"
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
                    wpercent = (basewidth / float(im.size[0]))
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
        if is_tiff(i):
            tiff = Tiff(i)
            ims = tiff.get_images()
        else:
            ims = [image.convert('RGB')]

        ims[0].save(o, save_all=True, append_images=ims)


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
                            xml_to_json(self.file_path, self.output_pathh)
                        # to YAML
                        if "yaml" in self.wmt:
                            xml_to_yaml(self.file_path, self.output_pathh)
                elif "image/" in self.cmt:
                    # Potential conversion
                    if "image/" in self.wmt:
                        image_to_any(self.file_path, self.output_path)
                        if not os.path.exists(self.output_path) and os.path.exists(self.output_path + ".tar.gz"):
                            self.output_path += ".tar.gz"
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
