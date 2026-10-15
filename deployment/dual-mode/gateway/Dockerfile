FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY deployment/dual-mode/gateway/requirements.txt ./
RUN python -m pip install --no-cache-dir --disable-pip-version-check -r requirements.txt
COPY deployment/dual-mode/gateway/app.py ./
ENV HOST=0.0.0.0 PORT=8880
EXPOSE 8880
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8880"]
