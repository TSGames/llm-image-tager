import base64
import json
import os
from io import BytesIO
from pathlib import Path
import logging
import time
import moondream

import ollama
import pyexiv2
from PIL import Image
from PIL.Image import Resampling
from transformers import AutoModelForCausalLM, AutoTokenizer
from PIL import Image


MODEL = os.getenv('MODEL', 'gemma3:4b')
PROMPT = os.getenv('PROMPT', 'Generate 5 - 10 keywords for this image and split them by ";"')
FIXED_KEYWORD = os.getenv('FIXED_KEYWORD', 'LLM-Generated')
OLLAMA_HOST = os.getenv('OLLAMA_HOST', 'http://ollama:11434')
IMAGE_PATH = os.getenv('IMAGE_PATH', '/mnt/images')
SLEEP_DURATION_SEC = os.getenv('SLEEP_DURATION_SEC', 60)
IMAGE_SIZE = os.getenv('IMAGE_SIZE', 128)


logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
)

ollama = ollama.Client(
  host = OLLAMA_HOST,
)

class LLM:
    def __init__(self):
        logging.info("Preparing model " + "vikhyatk/moondream2")
        self.model = moondream.vl(endpoint="http://localhost:2020/v1")
        # ollama.pull(MODEL)
        #self.model = AutoModelForCausalLM.from_pretrained(
        #    "vikhyatk/moondream2",
        #    revision="2025-04-14",
        #    trust_remote_code=True,
        #)

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
        existing = metadata.get('Iptc.Application2.Keywords', None)
        if existing and FIXED_KEYWORD in existing.value:
            logging.info('skipping classifying for ' + image_path)
            return
        logging.info('classifying  ' + image_path)

        image = Image.open(image_path).resize((IMAGE_SIZE, IMAGE_SIZE), resample=Resampling.BICUBIC)
        text = self.model.query(image, PROMPT)["answer"]
        keywords = [part.strip() for part in text.split(";") if part.strip()]
        logging.info(keywords)

        #data_uri = self.image_to_base64_data_uri(image_path)
        #                ChatCompletionRequestUserMessage(role='user', content=PROMPT)
        # response = ollama.chat(
        #     model=MODEL,
        #     messages=[{
        #         'role': 'user',
        #         'content': PROMPT,
        #         'images': [data_uri]
        #     }],
        #     format = {
        #         "type": "object",
        #         "properties": {
        #             "keywords": {
        #                 "type": "array",
        #                 "items": {
        #                     "type": "string"
        #                 }
        #             }
        #         },
        #         "required": [
        #             "keywords"
        #         ]
        #     }
        # )
        # keywords = json.loads(response.message.content)['keywords']
        if len(keywords) > 0:
            keywords = [k.capitalize() for k in keywords] + [FIXED_KEYWORD]
            if existing:
                keywords = list(set(keywords) | set(existing.value))
            logging.info(keywords)
            metadata['Iptc.Application2.Keywords'] = keywords
            metadata.write()
            os.utime(image_path)

    def classify_folder(self, folder_path):
        jpeg_files = [f for f in Path(folder_path).rglob("*") if f.suffix.lower() in ['.jpg', '.jpeg']]
        logging.info('Read ' + str(len(jpeg_files)) + ' files inside ' + folder_path)
        for file in jpeg_files:
            if any(part == "@eaDir" for part in file.parts):
                continue
            self.classify_file(str(file))
        logging.info("Finished classifying " + str(len(jpeg_files)) + " images")

llm = LLM()
while True:
    llm.classify_folder(IMAGE_PATH)
    logging.info("Sleeping for " + str(SLEEP_DURATION_SEC) + " seconds")
    time.sleep(SLEEP_DURATION_SEC)
