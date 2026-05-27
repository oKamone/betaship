FROM python:3.11-slim
WORKDIR /app
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY api/ .
COPY index.html .
EXPOSE 8080
CMD gunicorn proxy:app --bind 0.0.0.0:${PORT:-8080} --workers 1 --timeout 120
