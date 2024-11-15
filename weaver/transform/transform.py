import base64
import csv
import json
import os.path
import shutil
import tarfile
import tempfile
from typing import List

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

from weaver.formats import ContentType, get_extension
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

CONVERSION_DICT = {
    ContentType.TEXT_PLAIN: [ContentType.TEXT_PLAIN, ContentType.TEXT_HTML, ContentType.APP_PDF],
    ContentType.TEXT_HTML: [ContentType.TEXT_PLAIN, ContentType.APP_PDF],
    ContentType.IMAGE_PNG: [ContentType.IMAGE_GIF, ContentType.IMAGE_JPEG, ContentType.IMAGE_TIFF,
                            ContentType.IMAGE_SVG_XML, ContentType.APP_PDF],
    ContentType.IMAGE_GIF: [ContentType.IMAGE_PNG, ContentType.IMAGE_JPEG, ContentType.IMAGE_TIFF,
                            ContentType.IMAGE_SVG_XML, ContentType.APP_PDF],
    ContentType.IMAGE_JPEG: [ContentType.IMAGE_PNG, ContentType.IMAGE_GIF, ContentType.IMAGE_TIFF,
                             ContentType.IMAGE_SVG_XML, ContentType.APP_PDF],
    ContentType.IMAGE_TIFF: [ContentType.IMAGE_PNG, ContentType.IMAGE_GIF, ContentType.IMAGE_JPEG,
                             ContentType.IMAGE_SVG_XML, ContentType.APP_PDF],
    ContentType.IMAGE_SVG_XML: [ContentType.IMAGE_PNG, ContentType.IMAGE_GIF, ContentType.IMAGE_JPEG,
                                ContentType.IMAGE_TIFF, ContentType.APP_PDF],
    ContentType.TEXT_CSV: [ContentType.APP_XML, ContentType.APP_YAML, ContentType.APP_JSON],
    ContentType.APP_XML: [ContentType.APP_YAML, ContentType.APP_JSON],
    ContentType.APP_YAML: [ContentType.TEXT_CSV, ContentType.APP_XML, ContentType.APP_JSON],
    ContentType.APP_JSON: [ContentType.TEXT_CSV, ContentType.APP_XML, ContentType.APP_YAML]
}
EXCLUDED_TYPES = {ContentType.APP_RAW_JSON, ContentType.APP_OCTET_STREAM, ContentType.TEXT_PLAIN}


def exception_handler(func):
    """
    Decorator to handle exceptions in functions and log them.

    Args:
        func (Callable): Function to wrap with exception handling.

    Returns:
        Callable: The wrapped function.
    """
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
def image_to_any(i: str, out: str) -> None:
    """
    Converts image files to a specified output format. If no conversion is needed, it copies the file.

    Args:
        i (str): Input image file path.
        out (str): Output file path.
    """
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


def images_to_any(ims: List[Image.Image], out: str) -> None:
    """
    Processes a list of images and converts them to the desired format, saving them in the specified output path.

    Args:
        ims (List[Image.Image]): List of Image objects to process.
        out (str): Output file path.
    """
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
def any_to_html(i: str, out: str) -> None:
    """
    Converts any content type (text or image) to HTML format.

    Args:
        i (str): Input file path.
        out (str): Output file path.
    """
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
def any_to_pdf(i: str, out: str) -> None:
    """
    Converts a file to PDF format. If the file is an image, it is embedded in the PDF, otherwise, it is treated as text.

    Args:
        i (str): Input file path.
        out (str): Output PDF file path.
    """
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
def csv_to_json(i: str, out: str) -> None:
    """
    Converts a CSV file to a JSON file with a 'datas' key containing the rows.

    Args:
        i (str): Path to the input CSV file.
        out (str): Path to the output JSON file.
    """
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
def csv_to_xml(i: str, out: str) -> None:
    """
    Converts a CSV file to an XML file by first converting it to JSON.

    Args:
        i (str): Path to the input CSV file.
        out (str): Path to the output XML file.
    """
    file = f"{i}.json"
    csv_to_json(i, file)
    data = readfromjson(file)
    write_content(out, json2xml.Json2xml(data, item_wrap=False).to_xml())


@exception_handler
def json_to_xml(i: str, out: str) -> None:
    """
    Converts a JSON file to an XML file.

    Args:
        i (str): Path to the input JSON file.
        out (str): Path to the output XML file.
    """
    data = readfromjson(i)
    write_content(out, json2xml.Json2xml(data, item_wrap=False).to_xml())


@exception_handler
def json_to_txt(i: str, out: str) -> None:
    """
    Converts a JSON file to a text file.

    Args:
        i (str): Path to the input JSON file.
        out (str): Path to the output text file.
    """
    with open(i, "r", encoding="utf-8") as file:
        data = json.load(file)
    with open(out, "w", encoding="utf-8") as txt_file:
        json.dump(data, txt_file, indent=4)


@exception_handler
def json_to_yaml(i: str, out: str) -> None:
    """
    Converts a JSON file to a YAML file.

    Args:
        i (str): Path to the input JSON file.
        out (str): Path to the output YAML file.
    """
    with open(i, "r", encoding="utf-8") as file:
        configuration = json.load(file)
    with open(out, "w", encoding="utf-8") as yaml_file:
        yaml.dump(configuration, yaml_file)


@exception_handler
def yaml_to_json(i: str, out: str) -> None:
    """
    Converts a YAML file to a JSON file.

    Args:
        i (str): Path to the input YAML file.
        out (str): Path to the output JSON file.
    """
    with open(i, "r", encoding="utf-8") as file:
        configuration = yaml.safe_load(file)
    with open(out, "w", encoding="utf-8") as json_file:
        json.dump(configuration, json_file)


@exception_handler
def json_to_csv(i: str, out: str) -> None:
    """
    Converts a JSON file to a CSV file.

    Args:
        i (str): Path to the input JSON file.
        out (str): Path to the output CSV file.
    """
    with open(i, encoding="utf-8") as file:
        data_file = pd.read_json(file, encoding="utf-8")
        data_file.to_csv(out, encoding="utf-8", index=False)


@exception_handler
def xml_to_json(i: str, out: str) -> None:
    """
    Converts an XML file to a JSON file.

    Args:
        i (str): Path to the input XML file.
        out (str): Path to the output JSON file.
    """
    write_content(out, xmltodict.parse(get_content(i)))


@exception_handler
def html_to_txt(i: str, out: str) -> None:
    """
    Converts an HTML file to a text file.

    Args:
        i (str): Path to the input HTML file.
        out (str): Path to the output text file.
    """
    write_content(out, " ".join(BeautifulSoup(get_content(i), "html.parser").stripped_strings))


@exception_handler
def yaml_to_csv(i: str, out: str) -> None:
    """
    Converts a YAML file to a CSV file by first converting it to JSON.

    Args:
        i (str): Path to the input YAML file.
        out (str): Path to the output CSV file.
    """
    yaml_to_json(i, f"{i}.json")
    json_to_csv(f"{i}.json", out)


@exception_handler
def yaml_to_xml(i: str, out: str) -> None:
    """
    Converts a YAML file to an XML file by first converting it to JSON.

    Args:
        i (str): Path to the input YAML file.
        out (str): Path to the output XML file.
    """
    yaml_to_json(i, f"{i}.json")
    json_to_xml(f"{i}.json", out)


@exception_handler
def xml_to_yaml(i: str, out: str) -> None:
    """
    Converts an XML file to a YAML file by first converting it to JSON.

    Args:
        i (str): Path to the input XML file.
        out (str): Path to the output YAML file.
    """
    xml_to_json(i, f"{i}.json")
    json_to_yaml(f"{i}.json", out)


@exception_handler
def csv_to_yaml(i: str, out: str) -> None:
    """
    Converts a CSV file to a YAML file by first converting it to JSON.

    Args:
        i (str): Path to the input CSV file.
        out (str): Path to the output YAML file.
    """
    csv_to_json(i, f"{i}.json")
    json_to_yaml(f"{i}.json", out)


class Transform:
    """
    Class for handling the transformation of files between different media types (e.g., text, image, application).

    Attributes:
        file_path (str): The path to the input file to be transformed.
        current_media_type (str): The media type of the input file.
        wanted_media_type (str): The desired media type after transformation.
        output_path (str): The path where the transformed file will be saved.
        ext (str): The extension of the output file based on the wanted media type.

    Methods:
        process(): Initiates the file transformation process based on the input and output media types.
        get(): Returns a FileResponse with the transformed file for download.
    """

    def __init__(self, file_path: str, current_media_type: str, wanted_media_type: str):
        """
        Initializes the Transform object with file paths and media types.

        Args:
            file_path (str): Path to the file to be transformed.
            current_media_type (str): The media type of the input file.
            wanted_media_type (str): The desired media type for the output file.
        """
        self.file_path = file_path
        self.cmt = current_media_type.lower()
        self.wmt = wanted_media_type.lower()
        self.output_path = self.file_path

        self.ext = get_extension(self.wmt)

        if self.cmt != self.wmt:
            base_path, _ = os.path.splitext(self.file_path)
            self.output_path = base_path + self.ext
            if os.path.exists(self.output_path):
                try:
                    os.remove(self.output_path)
                except OSError as exc:
                    LOGGER.warning("Failed to delete [%s] err: %s", os.path.basename(self.output_path), exc)

    def process(self) -> None:
        """
        Processes the file based on the current and wanted media types and performs the transformation.

        Raises:
            RuntimeError: If an error occurs during the file transformation process.
        """
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

    def process_text(self) -> None:
        """
        Handles the transformation of text-based files (e.g., plain text, HTML, CSV).

        Raises:
            RuntimeError: If a conversion type is unsupported.
        """
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

    def process_csv(self) -> None:
        """
        Handles the conversion of CSV files to other formats like JSON, XML, and YAML.

        Raises:
            RuntimeError: If a conversion type is unsupported.
        """
        if "json" in self.wmt:
            csv_to_json(self.file_path, self.output_path)
        elif "xml" in self.wmt:
            csv_to_xml(self.file_path, self.output_path)
        elif "yaml" in self.wmt:
            csv_to_yaml(self.file_path, self.output_path)
        else:
            raise RuntimeError(f"Conversion from CSV to {self.wmt} is not supported.")

    def process_application(self) -> None:
        """
        Handles the conversion of application files (e.g., JSON, XML, YAML).

        Raises:
            RuntimeError: If a conversion type is unsupported.
        """
        if "json" in self.cmt:
            self.process_json()
        if "yaml" in self.cmt:
            self.process_yaml()
        if "xml" in self.cmt:
            self.process_xml()

    def process_json(self) -> None:
        """
        Handles the transformation of JSON files to other formats like CSV, XML, YAML, and plain text.

        Raises:
            RuntimeError: If a conversion type is unsupported.
        """
        if "csv" in self.wmt:
            json_to_csv(self.file_path, self.output_path)
        elif "xml" in self.wmt:
            json_to_xml(self.file_path, self.output_path)
        elif "yaml" in self.wmt:
            json_to_yaml(self.file_path, self.output_path)
        elif "plain" in self.wmt:
            json_to_txt(self.file_path, self.output_path)
        else:
            raise RuntimeError(f"Conversion from JSON to {self.wmt} is not supported.")

    def process_yaml(self) -> None:
        """
        Handles the conversion of YAML files to other formats like CSV, JSON, and XML.

        Raises:
            RuntimeError: If a conversion type is unsupported.
        """
        if "csv" in self.wmt:
            yaml_to_csv(self.file_path, self.output_path)
        elif "json" in self.wmt:
            yaml_to_json(self.file_path, self.output_path)
        elif "xml" in self.wmt:
            yaml_to_xml(self.file_path, self.output_path)
        else:
            raise RuntimeError(f"Conversion from YAML to {self.wmt} is not supported.")

    def process_xml(self) -> None:
        """
        Handles the conversion of XML files to JSON or YAML.

        Raises:
            RuntimeError: If a conversion type is unsupported.
        """
        if "json" in self.wmt:
            xml_to_json(self.file_path, self.output_path)
        elif "yaml" in self.wmt:
            xml_to_yaml(self.file_path, self.output_path)
        else:
            raise RuntimeError(f"Conversion from XML to {self.wmt} is not supported.")

    def process_image(self) -> None:
        """
        Handles the conversion of image files to other formats (e.g., image to image or image to PDF).

        Raises:
            RuntimeError: If a conversion type is unsupported.
        """
        if "image/" in self.wmt:
            image_to_any(self.file_path, self.output_path)
            if not os.path.exists(self.output_path) and os.path.exists(f"{self.output_path}.tar.gz"):
                self.output_path += ".tar.gz"
        elif "pdf" in self.wmt:
            any_to_pdf(self.file_path, self.output_path)
        else:
            raise RuntimeError(f"Conversion from img to {self.wmt} is not supported.")

    def get(self) -> FileResponse:
        """
        Returns the transformed file as a response for download.

        Returns:
            FileResponse: The response containing the transformed file.

        Raises:
            HTTPUnprocessableEntity: If an error occurs during file transformation.
        """
        try:
            if not os.path.exists(self.output_path):
                self.process()
            response = FileResponse(self.output_path)
            response.headers["Content-Disposition"] = f"attachment;  filename={os.path.basename(self.output_path)}"
            return response
        except Exception as err:
            raise HTTPUnprocessableEntity(json={
                "code": "JobOutputProcessingError",
                "description": "An error occurred while treating the output data",
                "cause": str(err),
                "error": type(err).__name__,
                "value": ""
            })
