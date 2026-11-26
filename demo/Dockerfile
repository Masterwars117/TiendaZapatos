FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY web/requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY web/*.py ./
COPY web/templates/ ./templates/
COPY web/static/ ./static/
COPY web/tests/ ./tests/
COPY demo/bootstrap.py ./bootstrap_demo.py
COPY demo/prepare_credentials.py .

CMD ["python", "-m", "flask", "--app", "app", "run", "--host=0.0.0.0", "--port=5000"]
