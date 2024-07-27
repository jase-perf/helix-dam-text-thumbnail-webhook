import sys
import logging
import io
from pathlib import Path
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import threading
from queue import Queue
import os
import logging
import sys
import tempfile
import base64

from flask import Flask, request, jsonify
import requests
from PIL import Image
from pygments import highlight
from pygments.lexers import get_lexer_for_filename
from pygments.formatters import ImageFormatter
from pygments.util import ClassNotFound

CUSTOM_FONT = "font/custom_font.ttf"

# Set these environment variables before running
DAM_URL = os.environ.get("DAM_URL")
ACCOUNT_KEY = os.environ.get("ACCOUNT_KEY")

FILETYPE_FIELD_NAME = "Coding Language"
FILETYPE_FIELD_UUID = None

NUM_WORKERS = 4

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s - %(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

process_queue = Queue()


def process_file(depot_path: str) -> None:
    logger.info(f"Downloading file: {depot_path}")
    # This is where you'd call your clip_extractor and handle the results
    with tempfile.TemporaryDirectory() as temp_dir:
        with open(Path(temp_dir) / Path(depot_path).name, "wb") as temp_file:
            try:
                download_file(depot_path, temp_file)
            except requests.exceptions.RequestException as e:
                logger.error(f"Error downloading file: {e}")
                return
        temp_file_path = Path(temp_dir) / Path(depot_path).name
        thumbnail_bytes, language_name = create_thumbnail(temp_file_path)
        if thumbnail_bytes:
            try:
                send_preview_to_dam(depot_path, thumbnail_bytes)
            except requests.exceptions.RequestException as e:
                logger.error(f"Error sending preview: {e}")
            try:
                send_metadata_to_dam(
                    depot_path,
                    metadata={
                        get_or_create_metadata_field(FILETYPE_FIELD_NAME): language_name
                    },
                )
            except requests.exceptions.RequestException as e:
                logger.error(f"Error sending metadata: {e}")


def download_file(depot_path: str, file_obj) -> None:
    url = f"{DAM_URL}/api/p4/files"
    headers = {"Authorization": f"account_key='{ACCOUNT_KEY}'"}
    response = requests.request(
        "GET", url, headers=headers, params={"depot_path": depot_path}
    )
    response.raise_for_status()
    for chunk in response.iter_content(chunk_size=8192):
        file_obj.write(chunk)


def send_preview_to_dam(depot_path: str, thumbnail_bytes: str) -> None:
    logger.info(f"Uploading preview image to DAM for {depot_path}")
    headers = {
        "Authorization": f"account_key='{ACCOUNT_KEY}'",
        "Content-Type": "application/json",
    }
    payload = {"content": thumbnail_bytes, "encoding": "base64"}
    params = {"depot_path": depot_path}
    response = requests.put(
        f"{DAM_URL}/api/p4/files/preview", headers=headers, params=params, json=payload
    )

    if response.status_code == 200:
        logger.info(f"Successfully uploaded preview image to DAM for {depot_path}")
        logger.debug(f"Response: {response.text}")
    else:
        logger.error(
            f"Failed to upload preview image to DAM for {depot_path}\n{response.status_code}: {response.text}"
        )


def send_metadata_to_dam(depot_path: str, metadata: dict) -> None:
    url = f"{DAM_URL}/api/p4/batch/custom_file_attributes"
    headers = {
        "Authorization": f"account_key='{ACCOUNT_KEY}'",
        "Content-Type": "application/json",
    }

    logger.debug(f"Adding metadata: {metadata}")
    payload = {
        "paths": [{"path": depot_path}],
        "create": [{"uuid": uuid, "value": value} for uuid, value in metadata.items()],
        "propagatable": False,
    }

    logger.debug(f"Sending metadata to DAM: {payload}")
    response = requests.put(
        url,
        headers=headers,
        json=payload,
    )
    response.raise_for_status()
    logger.info(f"Successfully uploaded metadata to DAM for {depot_path}")


@lru_cache(maxsize=1)
def get_or_create_metadata_field(field_name: str) -> str:
    url = f"{DAM_URL}/api/company/file_attribute_templates"
    headers = {"Authorization": f"account_key='{ACCOUNT_KEY}'"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    all_fields = response.json()["results"]

    field_uuid = next((f["uuid"] for f in all_fields if f["name"] == field_name), None)

    if field_uuid:
        return field_uuid

    payload = {
        "name": field_name,
        "type": "text",
        "available_values": [],
        "hidden": False,
    }
    response = requests.post(
        url,
        headers=headers,
        json=payload,
    )
    response.raise_for_status()
    field_uuid = response.json()["uuid"]
    return field_uuid


def create_thumbnail(file_path, size=(240, 240), font_size=8):
    logger.info(f"Creating thumbnail for {file_path}")
    content = read_file_content(file_path)

    lexer = get_lexer(file_path)
    formatter = get_formatter(font_size, size[0] * 2)

    byte_io = io.BytesIO()
    byte_io.write(highlight(content, lexer, formatter))
    byte_io.seek(0)

    img = Image.open(byte_io)

    # Crop to square from top-left
    crop_size = min(img.size)
    img = img.crop((0, 0, crop_size, crop_size))

    # Resize to target size
    img = img.resize(size, Image.BILINEAR)

    # Instead of saving to file, save to bytes
    output_byte_io = io.BytesIO()
    img.save(output_byte_io, format="PNG", optimize=True, quality=85)
    img_byte_arr = output_byte_io.getvalue()
    # Convert to base64
    base64_encoded = base64.b64encode(img_byte_arr).decode("utf-8")

    return base64_encoded, lexer.name


def read_file_content(file_path, max_length=500):
    encodings = ["utf-8", "latin-1", "ascii", "utf-16", "utf-32"]
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read(max_length)
                logger.debug(f"Read file {file_path} with encoding {encoding}")
                if content.strip():  # Check if content is not just whitespace
                    return content
        except UnicodeDecodeError:
            continue

    # If all encodings fail, read as binary and decode with replacement
    logger.debug(f"Fallback to read file{file_path} as bytes")
    with open(file_path, "rb") as f:
        binary_content = f.read(max_length)

    # Try to decode the binary content without replacements
    for encoding in encodings:
        try:
            return binary_content.decode(encoding)
        except UnicodeDecodeError:
            continue

    # If all decoding attempts fail, fall back to a safe representation
    printable_content = "".join(
        char
        for char in binary_content.decode("ascii", errors="ignore")
        if char.isprintable()
    )
    return f"{printable_content}"


@lru_cache(maxsize=32)
def get_lexer(filename):
    try:
        return get_lexer_for_filename(filename)
    except ClassNotFound:
        return None


def get_formatter(font_size, image_width):
    formatter_kwargs = {
        "font_size": font_size,
        "line_numbers": False,
        "image_width": image_width,
        "image_pad": 10,
        "encoding": "utf-8",
    }

    if Path(CUSTOM_FONT).is_file():
        logger.info("Using custom font")
        formatter_kwargs["font_name"] = Path(CUSTOM_FONT)

    return ImageFormatter(**formatter_kwargs)


def worker(depot_path):
    try:
        process_file(depot_path)
    except Exception as e:
        logger.exception(f"Error processing file: {depot_path}. {e}")


def executor_main():
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        while True:
            depot_path = process_queue.get()
            executor.submit(worker, depot_path)


# Start worker thread
threading.Thread(target=executor_main, daemon=True).start()


@app.route("/webhook", methods=["POST"])
def webhook():
    logging.debug(f"Received webhook request. {request}")
    data = request.json
    if not data:
        logging.error("No JSON data in request")
        return jsonify({"error": "No JSON data in request"}), 400

    files_to_process = []

    for update in data:
        if (
            "objects" not in update
            or "files" not in update["objects"]
            or (
                "added" not in update["objects"]["files"]
                and "modified" not in update["objects"]["files"]
            )
        ):
            logging.warning(
                "Skipping update: No added or modified 'objects' or 'files' in update"
            )
            logging.debug(str(update))
            continue

        for action in ["added", "modified"]:
            for depot_path in update["objects"]["files"][action]:
                if get_lexer(Path(depot_path).name) is None:
                    logger.debug(
                        f"Skipping file {Path(depot_path).name}: No lexer found"
                    )
                else:
                    files_to_process.append(depot_path)

    for depot_path in files_to_process:
        process_queue.put(depot_path)

    return (
        jsonify({"message": f"Queued {len(files_to_process)} files for processing"}),
        200,
    )


if __name__ == "__main__":
    if not DAM_URL or not ACCOUNT_KEY:
        logger.error("DAM_URL and ACCOUNT_KEY must be set as environment variables")
        exit(1)
    app.run(host="0.0.0.0", port=8080, debug=False)
