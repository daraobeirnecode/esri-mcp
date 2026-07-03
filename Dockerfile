FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY esri_mcp ./esri_mcp
RUN pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1
# Cloud Run provides PORT; esri_mcp.server.main() switches to streamable-http when set
CMD ["python", "-m", "esri_mcp"]
