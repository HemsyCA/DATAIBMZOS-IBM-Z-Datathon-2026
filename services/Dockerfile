# One image for all four services, built on the IBM LinuxONE Jupyter image, which already ships
# s390x builds of numpy, pandas, xgboost, PyTorch with torch_nnpa (Telum II NNPA) and llama.cpp with zDNN.
# Check the exact image name on the VM with: docker inspect notebook --format '{{.Config.Image}}'
ARG BASE_IMAGE=registry.linuxone.cloud.marist.edu/l1cc/jupyterlab-image-s390x:latest
FROM ${BASE_IMAGE}

USER root
# Only pure-Python/available-on-s390x packages (Streamlit is NOT usable: it needs pyarrow, which has no s390x build)
RUN python -m pip install --no-cache-dir fastapi uvicorn requests

WORKDIR /app
COPY security /app/security
COPY services /app/services

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    TORCHDYNAMO_DISABLE=1 \
    HOME=/tmp

ENTRYPOINT []
CMD ["python", "-c", "print('Pick a service command in docker-compose.yml')"]
