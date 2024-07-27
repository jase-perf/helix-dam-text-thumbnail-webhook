FROM python:3.12.4-slim-bookworm


RUN apt-get update && apt-get install -y \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY font/* .

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY text_preview_webhook.py .

CMD ["python", "text_preview_webhook.py"]