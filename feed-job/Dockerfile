# Nightly NBA feed job (Shams v2).
#
# Refreshes box scores from nba_api into the mounted ~/.shams cache, then publishes the
# static feed the season extension reads to the repo's `feed` branch. No Yahoo
# credentials: see docs/shams-v2.md. Build from the repo root:
#
#   docker build -f feed-job/Dockerfile -t shams-feed .
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# The same dependencies as the backend, which runs the same tools/ code.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim

WORKDIR /app

# git and ssh push the feed. GitHub's host keys are recorded at build time so the push
# keeps strict host key checking without a first-connect prompt.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    && rm -rf /var/lib/apt/lists/* \
    && ssh-keyscan -t ed25519,ecdsa,rsa github.com > /etc/ssh/ssh_known_hosts \
    && test -s /etc/ssh/ssh_known_hosts

COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1

COPY tools /app/tools
COPY scripts /app/scripts

# Box scores are final by ~03:00 Eastern; 05:00 leaves room for stragglers.
CMD ["python", "scripts/nightly_feed.py", "--at", "05:00"]
