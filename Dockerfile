#FROM python:3.10-slim
FROM ubuntu:24.04

RUN apt-get update
RUN apt-get install curl python3 python3-pip build-essential cmake  python3-all-dev libexiv2-dev python3-dev libboost-python-dev -y


# 2. Arbeitsverzeichnis im Container setzen
WORKDIR /app

# 3. Requirements zuerst kopieren und installieren (Docker Cache nutzen)
COPY requirements.txt .

RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

RUN curl https://depot.moondream.ai/station/install.sh | bash

#RUN useradd -m appuser
#RUN mkdir -p /mnt/images && chown appuser:appuser /mnt/images


# 4. Den restlichen Code ins Image kopieren
COPY . .

#USER appuser

CMD ["sh", "-c", "./moondream_station <<EOF\\nexit\\nEOF && python3 llm.py && wait"]