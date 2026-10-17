FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY chainbreaker ./chainbreaker
COPY web ./web
COPY data/snapshots ./data/snapshots
COPY data/replay_tj_2025.json data/demo_ground_truth.json ./data/
RUN pip install --no-cache-dir .
ENV PYTHONUNBUFFERED=1 CB_ROOT=/app
CMD ["uvicorn", "chainbreaker.api:app", "--host", "0.0.0.0", "--port", "8000"]
