# Pin PYTHON_IMAGE to an approved digest for a production release.
ARG PYTHON_IMAGE=python:3.12-slim-bookworm
FROM ${PYTHON_IMAGE} AS builder
WORKDIR /build
COPY requirements-build.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements-build.lock
COPY pyproject.toml ./
COPY src ./src
RUN pip wheel --no-deps --no-build-isolation --wheel-dir /wheels .

FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 VEILGATE_CONFIG=/config/policy.toml
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-deps /wheels/*.whl
USER 65532:65532
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=2).close()"]
ENTRYPOINT ["veilgate"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
