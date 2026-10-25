FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 DEEPEVAL_TELEMETRY_OPT_OUT=YES
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --default-timeout=120 .

COPY prompts ./prompts
COPY data ./data

# Mount /state to keep run history and reports between runs.
ENTRYPOINT ["python", "-m", "regress"]
CMD ["run", "--db", "/state/runs.db", "--out", "/state/reports"]
