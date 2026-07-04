FROM python:3.11-slim

WORKDIR /code

# Sentence-transformers/torch try to write cache to the home dir by
# default, but HF Spaces containers only allow writes to /tmp.
# Redirecting the cache here avoids permission errors on model load.
ENV HF_HOME=/tmp/huggingface
ENV TRANSFORMERS_CACHE=/tmp/huggingface
ENV SENTENCE_TRANSFORMERS_HOME=/tmp/huggingface

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# HF Spaces always expects the container to listen on 7860
EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
