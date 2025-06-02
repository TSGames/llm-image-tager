#FROM python:3.10-slim
FROM ubuntu:24.04

RUN apt-get update
RUN apt-get install python3 build-essential cmake python3-all-dev libexiv2-dev python3-dev libboost-python-dev -y

# 2. Arbeitsverzeichnis im Container setzen
WORKDIR /app

# 3. Requirements zuerst kopieren und installieren (Docker Cache nutzen)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt


# 4. Den restlichen Code ins Image kopieren
COPY . .

USER appuser

CMD ["python", "llm.py"]