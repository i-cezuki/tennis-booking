FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

# The entrypoint process runs as PID 1 with no real init, so it never reaps
# orphaned children -- Chromium (chrome + chrome_crashpad, x2 each) leaves
# zombies behind on every launch even after browser.close(). On a Lambda
# execution environment reused across many invocations these accumulate
# without bound until the container hits its process-table limit and every
# subsequent Chromium launch starts failing (reproduced locally: ps showed
# 4 new <defunct> processes per fetch_availability() call, never reaped).
# tini as PID 1 reaps them automatically.
RUN apt-get update -qq && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /var/task

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt awslambdaric

COPY src ./src

# scraper.py writes a relative "failure.png" on scrape failure and is not
# modified by this migration. /var/task is read-only at runtime, so the
# working directory is switched to /tmp (the only writable path in Lambda)
# while keeping the code importable via PYTHONPATH.
ENV PYTHONPATH=/var/task
WORKDIR /tmp

ENTRYPOINT ["/usr/bin/tini", "--", "python", "-m", "awslambdaric"]
CMD ["src.main.lambda_handler"]
