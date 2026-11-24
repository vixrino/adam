FROM docker.bdistrib-build.sofact.banque-france.fr/bdf/exa/devsecops/python/bdf-python312:2.0.41

ARG ARTIFACT_DIR=src

WORKDIR /opt/app-root/src/

COPY requirements.txt .
COPY ${ARTIFACT_DIR} .
COPY launcher.py .
COPY conf conf
COPY https.truststore.pem .

RUN python -m venv .venv && \
    source .venv/bin/activate && \
    python -m pip install -r requirements.txt --no-cache-dir

ENV PATH="/opt/app-root/src/.venv/bin:$PATH"

CMD ["python", "-m", "src.TODO"]
