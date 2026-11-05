# TFF environment for machines without Linux x86_64 (e.g. macOS).
# The install steps match the tested recipe in README; this Dockerfile
# itself was NOT tested. On Apple Silicon it runs under emulation (slow).
#   docker build --platform linux/amd64 -t fl-tff env/
#   docker run --platform linux/amd64 --rm -it -v "$PWD":/work -w /work fl-tff python env/check_tff.py
FROM --platform=linux/amd64 python:3.11-slim
RUN pip install --no-cache-dir uv
COPY tff-overrides.txt /tmp/tff-overrides.txt
RUN uv pip install --system --no-cache "tensorflow-federated==0.87.0" pandas pyarrow \
        --override /tmp/tff-overrides.txt
