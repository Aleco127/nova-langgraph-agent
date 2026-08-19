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
    /opt/venv/bin/pip install . && \
    # The installer comes back out once there is nothing left to install. This
    # is a security change, not housekeeping: pip vendors its own copies of
    # msgpack and setuptools, and those two accounted for the Python-side HIGH
    # findings that failed this build. It also means a process that gets code
    # execution in this container has no package manager to fetch its next
    # stage with.
    rm -rf /opt/venv/lib/python3.12/site-packages/pip \
           /opt/venv/lib/python3.12/site-packages/pip-*.dist-info \
           /opt/venv/bin/pip*


FROM python:3.12-slim AS runtime

# A published base image lags the security archive by however long it has been
# since it was last rebuilt, and nine HIGH findings in the util-linux family
# came out of exactly that gap. Upgrading closes it at build time, which is the
# honest fix; adding nine lines to .trivyignore would only have hidden it.
RUN apt-get update && \
    apt-get upgrade -y && \
    rm -rf /var/lib/apt/lists/*

# Same reasoning as the builder, applied to the interpreter the base image
# ships. Nothing in the runtime path imports pip.
RUN rm -rf /usr/local/lib/python3.12/site-packages/pip \
           /usr/local/lib/python3.12/site-packages/pip-*.dist-info \
           /usr/local/bin/pip*

# No apt-get install at all. The entry point reads argv and writes stdout, so
# it needs neither curl nor a shell utility, and a package that is not
# installed is a package Trivy cannot find a CVE in.
RUN useradd --create-home --uid 1000 app

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER app
WORKDIR /home/app

ENTRYPOINT ["python", "-m", "nova_agent"]
