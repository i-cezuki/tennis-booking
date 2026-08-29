FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

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

ENTRYPOINT ["python", "-m", "awslambdaric"]
CMD ["src.main.lambda_handler"]
