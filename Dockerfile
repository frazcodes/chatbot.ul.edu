FROM python:3.11-slim
WORKDIR /srv
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY static ./static
# Build the index first on your machine (crawler + ingest) and mount ./data as a volume:
#   docker run -p 8000:8000 --env-file .env -v $(pwd)/data:/srv/data ul-chatbot
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
