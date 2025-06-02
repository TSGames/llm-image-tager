import base64
import json
import os
from io import BytesIO
from pathlib import Path
import logging
import time

import ollama
import pyexiv2
from PIL import Image
from PIL.Image import Resampling

MODEL = os.getenv('MODEL', 'gemma3:4b')
PROMPT = os.getenv('PROMPT', 'Erzeuge 5 bis 10 passende Schlagworte für dieses Bild in Deutsch.')
FIXED_KEYWORD = os.getenv('FIXED_KEYWORD', 'LLM-Generated')
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://ollama:11434')
SLEEP_DURATION_SEC = os.getenv('SLEEP_DURATION_SEC', 60)


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

    def image_to_base64_data_uri(self, image_path):
        # Lade das Bild
        # 896
        image_resized = Image.open(image_path).resize((896, 896), resample=Resampling.BICUBIC).convert("RGB")
        buffered = BytesIO()
        image_resized.save(buffered, format="JPEG", quality=90)
        img_bytes = buffered.getvalue()

        # Bytes zu Base64 string
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        return f"{img_base64}"

    def classify_file(self, image_path: str):
        metadata = pyexiv2.ImageMetadata(image_path)
        metadata.read()
        existing = metadata.get('Iptc.Application2.Keywords', None)
        if existing and FIXED_KEYWORD in existing.value:
            logging.info('skipping tagging for ' + image_path)
            return
        logging.info('tagging  ' + image_path)
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
        keywords = json.loads(response.message.content)['keywords']
        logging.info(keywords)
        if len(keywords) > 0:
            keywords = keywords + [FIXED_KEYWORD]
            if existing:
                keywords = list(set(keywords) | set(existing.value))
            logging.info(keywords)
            metadata['Iptc.Application2.Keywords'] = keywords
            metadata.write()

    def classify_folder(self, folder_path):
        jpeg_files = [f for f in Path(folder_path).rglob("*") if f.suffix.lower() in ['.jpg', '.jpeg']]
        for file in jpeg_files:
            self.classify_file(str(file))
        logging.info("Finished classifying " + str(len(jpeg_files)) + " images")


while True:
    LLM().classify_folder("/mnt/images")
    logging.info("Sleeping for " + str(SLEEP_DURATION_SEC) + " seconds")
    time.sleep(SLEEP_DURATION_SEC)
