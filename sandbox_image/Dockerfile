FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib

RUN apt-get update \
    && apt-get install -y --no-install-recommends coreutils procps \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 1000 sandbox

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

RUN mkdir -p /workspace \
    && chown sandbox:sandbox /workspace \
    && printf 'unmodified' > /cage-readonly-canary \
    && chmod 0666 /cage-readonly-canary

WORKDIR /workspace
USER sandbox
CMD ["sleep", "infinity"]
