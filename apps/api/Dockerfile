FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ARG DEV=false
COPY requirements*.txt ./
RUN pip install --no-cache-dir -r $([ "$DEV" = "true" ] && echo requirements-dev.txt || echo requirements.txt)
COPY . .
RUN useradd -m app && chown -R app /app
USER app
ENV PORT=8000
# 같은 이미지로 worker도 실행한다: python -m preflight.worker
CMD ["sh", "-c", "uvicorn preflight.main:app --host 0.0.0.0 --port $PORT"]
