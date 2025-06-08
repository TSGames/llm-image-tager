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
# if you want to use multiple hosts (ordered by priority), split with ","
OLLAMA_HOSTS = os.getenv('OLLAMA_HOSTS', 'http://ollama:11434').split(",")
# in seconds
OLLAMA_SWITCH_DELAY = int(os.getenv('OLLAMA_SWITCH_DELAY', '60'))
IMAGE_PATH = os.getenv('IMAGE_PATH', '/mnt/images')
SLEEP_DURATION_SEC = int(os.getenv('SLEEP_DURATION_SEC', 60))
IMAGE_SIZE = int(os.getenv('IMAGE_SIZE', 896))
MAX_RETRIES = int(os.getenv('MAX_RETRIES', 3))

M_TIME_FILE = "m_time"
Path(M_TIME_FILE).parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
)

class LLM:
    ollama = None
    min_m_time = None
    retryOllama = time.time()
    def __init__(self):
        logging.info("Preparing model " + MODEL)
        self.check_ollama(True)
        try:
            self.min_m_time = float(next(open(M_TIME_FILE)))
        except FileNotFoundError as e:
            pass
    def check_ollama(self, force = False):
        if self.ollama and len(OLLAMA_HOSTS) == 1:
            return
        if force or time.time() - self.retryOllama > OLLAMA_SWITCH_DELAY:
            for host in OLLAMA_HOSTS:
                try:
                    self.ollama = ollama.Client(
                        host=host,
                    )
                    self.ollama.pull(MODEL)

                    logging.info("ollama at " + host + " will be used")
                    break
                except Exception as e:
                    logging.info("ollama at " + host + " currently unreachable, trying other")
                    pass

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
        mtime = os.stat(image_path).st_mtime
        if self.min_m_time and mtime < self.min_m_time:
            logging.debug('skipping classifying for ' + image_path + " (is older than last run)")
            return
        metadata = pyexiv2.ImageMetadata(image_path)
        metadata.read()
        existing_tags = metadata.get('Iptc.Application2.Keywords', None)
        if existing_tags and FIXED_TAG in existing_tags.value:
            logging.debug('skipping classifying for ' + image_path)
            return
        if SKIP_MANUALLY_TAGGED and (len(existing_tags.value) if existing_tags else 0) > 0:
            logging.debug('skipping manually tagged file ' + image_path)
            return
        logging.info('classifying  ' + image_path)
        data_uri = self.image_to_base64_data_uri(image_path)
        #                ChatCompletionRequestUserMessage(role='user', content=PROMPT)
        self.check_ollama()
        response = self.ollama.chat(
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
            atime = os.stat(image_path).st_atime,
            metadata.write()
            os.utime(image_path, (atime, mtime))
            #self.delete_matching_eadir_files(image_path)

    def classify_folder(self, folder_path: str):
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
                    self.check_ollama(True)
                    logging.warning('classifying  ' + str(file) + 'failed' + str(e))
                    time.sleep(1 * i)
                    pass
        logging.info("Finished classifying " + str(len(jpeg_files)) + " images inside " + folder_path)
        with open(M_TIME_FILE, "w") as f:
            f.write(str(time.time()))
        for folder in [f for f in Path(folder_path).glob("*") if f.is_dir() and not any(part == "@eaDir" for part in Path(f).parts)]:
            self.classify_folder(str(folder))

llm = LLM()
while True:
    llm.classify_folder(IMAGE_PATH)
    logging.info("Sleeping for " + str(SLEEP_DURATION_SEC) + " seconds")
    time.sleep(SLEEP_DURATION_SEC)
