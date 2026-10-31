FROM python:3.11-slim
WORKDIR /srv
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Best effort: pre-download the embedding model during build so cold starts
# are fast. If this fails for any reason, the app simply downloads the model
# at first startup instead, so the build must not depend on it.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small')" || echo "model bake skipped; will download at startup"
COPY app ./app
COPY static ./static
# The search index is committed in the repo (small, ~5 MB):
COPY data ./data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
