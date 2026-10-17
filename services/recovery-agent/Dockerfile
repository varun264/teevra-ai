FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8072
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir pydantic pydantic-settings tzdata ortools fastapi uvicorn httpx a2a-sdk
COPY . /app
RUN pip install --no-cache-dir -e /app/packages/shared-schemas \
    && pip install --no-cache-dir -e /app/packages/simulation \
    && pip install --no-cache-dir -e /app/packages/a2a \
    && pip install --no-cache-dir -e /app/services/scheduler-engine
EXPOSE 8072
CMD ["python", "services/recovery-agent/main.py"]
