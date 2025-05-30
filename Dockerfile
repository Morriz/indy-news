FROM python:3.11 as base
WORKDIR /app
COPY requirements.txt /app/
RUN python -m venv .venv
RUN .venv/bin/pip install --no-cache-dir -r requirements.txt

FROM base as ci
RUN .venv/bin/pip install --no-cache-dir -r requirements-test.txt

FROM ci as test
COPY . /app
RUN bin/format.sh && bin/lint.sh && bin/test.sh

FROM python:3.11-slim
WORKDIR /app
COPY --from=base /app /app
COPY . /app

CMD ["./start.sh"]