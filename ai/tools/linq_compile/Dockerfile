# Окружение компилятора LinQ TPU (SDK поставляется только под linux x86_64 / Python 3.12).
# Колёса SDK: распакуйте vendor/linq_sdk/Framework/tpu_framework_2026.9.45.zip и положите packets/ рядом.
#   docker build --platform linux/amd64 -t linq-tpu-compiler:2026.9.45 tools/linq_compile
FROM --platform=linux/amd64 python:3.12.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*
ENV PIP_DEFAULT_TIMEOUT=120
# torch из CPU-индекса: без CUDA-библиотек образ легче на ~3 ГБ
RUN pip install --no-cache-dir torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cpu
COPY packets /packets
RUN cd /packets && pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir opencv-python-headless pillow pyyaml
WORKDIR /work
