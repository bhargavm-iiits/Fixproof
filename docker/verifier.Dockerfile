FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 runner

WORKDIR /work
COPY target_app/requirements.txt /tmp/requirements.txt
COPY docker/verifier-requirements.txt /tmp/verifier-requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt -r /tmp/verifier-requirements.txt

COPY docker/run_tests.py /usr/local/bin/run_tests.py
USER runner
ENTRYPOINT ["python", "/usr/local/bin/run_tests.py"]
