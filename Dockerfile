# Multi-stage: the venv is built here and copied over, so no build toolchain,
# no pip cache and no source tree reach the runtime image. Less to scan, and
# fewer packages that could carry a CVE the agent never executes.
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build

COPY pyproject.toml ./
COPY src/ ./src/
RUN python -m venv /opt/venv && \
    /opt/venv/bin/pip install --upgrade pip && \
    /opt/venv/bin/pip install .


FROM python:3.12-slim AS runtime

# No apt-get install at all. The entry point is a Python process that reads
# argv and writes stdout, so it needs neither curl nor a shell utility, and
# every package not installed is a package Trivy cannot find a CVE in.
RUN useradd --create-home --uid 1000 app

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app
WORKDIR /home/app

ENTRYPOINT ["python", "-m", "nova_agent"]
