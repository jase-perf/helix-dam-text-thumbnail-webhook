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

import chardet
from flask import Flask, request, jsonify
import requests
from PIL import Image
from pygments import highlight
from pygments.lexers import get_lexer_for_filename
from pygments.formatters import ImageFormatter
from pygments.util import ClassNotFound
from helixdam import HelixDAM, HelixDAMAuthException, HelixDAMException

CUSTOM_FONT = "font/custom_font.ttf"

# Set these environment variables before running
DAM_URL = os.environ.get("DAM_URL")
ACCOUNT_KEY = os.environ.get("ACCOUNT_KEY")

FILETYPE_FIELD_NAME = "Coding Language"

NUM_WORKERS = 4

hd = HelixDAM(account_key=ACCOUNT_KEY, url=DAM_URL)


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
        temp_file_path = Path(temp_dir) / Path(depot_path).name
        try:
            hd.download_file(depot_path, temp_file_path)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error downloading file: {e}")
            return
        thumbnail_bytes, language_name = create_thumbnail(temp_file_path)
        if thumbnail_bytes:
            try:
                hd.upload_preview(depot_path, input_bytes=thumbnail_bytes)
                logger.info(f"Successfully uploaded preview for {depot_path}")
            except HelixDAMException as e:
                logger.error(f"Error sending preview: {e}")
            try:
                hd.update_file_metadata_by_name(
                    depot_path,
                    name_value_dict={FILETYPE_FIELD_NAME: language_name},
                )
                logger.info(f"Successfully updated metadata for {depot_path}")
            except HelixDAMException as e:
                logger.error(f"Error sending metadata: {e}")

def create_thumbnail(file_path, size=(512, 512), font_size=16):
    logger.info(f"Creating thumbnail for {file_path}")
    content = read_file_content(file_path)

    lexer = get_lexer(file_path)
    formatter = get_formatter(font_size=font_size, image_pad=10, line_pad=5)

    byte_io = io.BytesIO()
    byte_io.write(highlight(content, lexer, formatter))
    byte_io.seek(0)

    img = Image.open(byte_io)
    bg_color = img.getpixel((0, 0))
    content_box = img.getbbox()
    img = img.crop(content_box)

    thumbnail = Image.new("RGB", size, color=bg_color)

    # Calculate position to center the image
    offset = (
        (size[0] - img.width) // 2 if img.width < size[0] else 0,
        (size[1] - img.height) // 2 if img.height < size[1] else 0,
    )
    thumbnail.paste(img, offset)

    # Instead of saving to file, save to bytes
    buffer = io.BytesIO()
    thumbnail.save(buffer, format="PNG", optimize=True, quality=85)
    base64_encoded = buffer.getvalue()

    return base64_encoded, lexer.name


def read_file_content(file_path, max_length=500):
    with open(file_path, "rb") as f:
        raw_data = f.read(max_length)

    detected = chardet.detect(raw_data)
    encoding = detected["encoding"]
    logger.debug(f"Detected encoding: {encoding}")

    try:
        return raw_data.decode(encoding)
    except UnicodeDecodeError:
        logger.warning(f"Failed to decode file content: {file_path}")
        return raw_data.decode("utf-8", errors="ignore")

@lru_cache(maxsize=32)
def get_lexer(filename):
    try:
        return get_lexer_for_filename(filename)
    except ClassNotFound:
        return None


def get_formatter(font_size, image_pad, line_pad):
    formatter_kwargs = {
        "font_size": font_size,
        "line_numbers": False,
        "image_pad": 10,
        "line_pad": 5,
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
