import base64
import json
import os
from io import BytesIO
from pathlib import Path
import logging
import time
import shutil

import ollama
import pyexiv2
from PIL import Image
from PIL.Image import Resampling
from PIL.ImageOps import expand

MODEL = os.getenv('MODEL', 'gemma3:4b')
PROMPT = os.getenv('PROMPT', 'Erzeuge 5 bis 10 passende Schlagworte für dieses Bild in Deutsch.')
FIXED_TAG = os.getenv('FIXED_TAG', 'LLM-Generated')
KEEP_EXISTING_TAGS = os.getenv('KEEP_EXISTING_TAGS', 'true').lower() == 'true'
# Skip images already having tags but not the FIXED_TAG assigned
SKIP_MANUALLY_TAGGED = os.getenv('SKIP_MANUALLY_TAGGED', 'true').lower() == 'true'
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://ollama:11434')
IMAGE_PATH = os.getenv('IMAGE_PATH', '/mnt/images')
SLEEP_DURATION_SEC = int(os.getenv('SLEEP_DURATION_SEC', 60))
IMAGE_SIZE = int(os.getenv('IMAGE_SIZE', 896))
MAX_RETRIES = int(os.getenv('MAX_RETRIES', 3))


logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
)

ollama = ollama.Client(
  host = OLLAMA_HOST,
)

class LLM:
    def __init__(self):
        logging.info("Preparing model " + MODEL)
        ollama.pull(MODEL)

    # does not work / has no effect
    def delete_matching_eadir_files(self, image_path):
        if not os.path.isfile(image_path):
            return
        filename = os.path.basename(image_path)
        root_dir = os.path.dirname(image_path) + "/@eaDir/"
        shutil.rmtree(root_dir + filename, ignore_errors=True)
        try:
            os.unlink(root_dir + filename + "@SynoEAStream")
            logging.info(f"Deleted metadata for {filename}")
        except Exception as e:
            logging.error(f"Error deleting metadata for {filename}: {e}")

    def image_to_base64_data_uri(self, image_path):
        # 896
        logging.info('resizing to ' + str(IMAGE_SIZE))
        image_resized = Image.open(image_path).resize((IMAGE_SIZE, IMAGE_SIZE), resample=Resampling.BICUBIC).convert("RGB")
        buffered = BytesIO()
        image_resized.save(buffered, format="JPEG", quality=90)
        img_bytes = buffered.getvalue()

        # Bytes zu Base64 string
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        logging.info('resizing done')
        return f"{img_base64}"

    def classify_file(self, image_path: str):
        metadata = pyexiv2.ImageMetadata(image_path)
        metadata.read()
        existing_tags = metadata.get('Iptc.Application2.Keywords', None)
        if existing_tags and FIXED_TAG in existing_tags.value:
            logging.info('skipping classifying for ' + image_path)
            return
        if SKIP_MANUALLY_TAGGED and (len(existing_tags.value) if existing_tags else 0) > 0:
            logging.info('skipping manually taged file ' + image_path)
            return
        logging.info('classifying  ' + image_path)
        data_uri = self.image_to_base64_data_uri(image_path)
        #                ChatCompletionRequestUserMessage(role='user', content=PROMPT)
        response = ollama.chat(
            model=MODEL,
            messages=[{
                'role': 'user',
                'content': PROMPT,
                'images': [data_uri]
            }],
            format = {
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        }
                    }
                },
                "required": [
                    "keywords"
                ]
            }
        )
        tags = json.loads(response.message.content)['keywords']
        logging.info(tags)
        if len(tags) > 0:
            tags = [t[:1].upper() + t[1:] for t in tags] + [FIXED_TAG]
            if KEEP_EXISTING_TAGS and existing_tags:
                tags = list(set(tags) | set(existing_tags.value))
            logging.info(tags)
            metadata['Iptc.Application2.Keywords'] = tags
            atime, mtime = os.stat(image_path).st_atime, os.stat(image_path).st_mtime
            metadata.write()
            os.utime(image_path, (atime, mtime))
            #self.delete_matching_eadir_files(image_path)

    def classify_folder(self, folder_path):
        jpeg_files = [f for f in Path(folder_path).glob("*") if f.suffix.lower() in ['.jpg', '.jpeg']]
        logging.info('Read ' + str(len(jpeg_files)) + ' files inside ' + folder_path)
        for file in jpeg_files:
            if any(part == "@eaDir" for part in file.parts):
                continue
            for i in range(0,MAX_RETRIES):
                try:
                    self.classify_file(str(file))
                    break
                except Exception as e:
                    logging.warning('classifying  ' + str(file) + 'failed' + str(e))
                    time.sleep(1 * i)
                    pass
        logging.info("Finished classifying " + str(len(jpeg_files)) + " images inside ' + folder_path")
        for folder in [f for f in Path(folder_path).glob("*") if f.is_dir() and not any(part == "@eaDir" for part in Path(f).parts)]:
            self.classify_folder(folder)

llm = LLM()
while True:
    llm.classify_folder(IMAGE_PATH)
    logging.info("Sleeping for " + str(SLEEP_DURATION_SEC) + " seconds")
    time.sleep(SLEEP_DURATION_SEC)
