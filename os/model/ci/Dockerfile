FROM debian:trixie-slim
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3 libstdc++6 libgomp1 ca-certificates && rm -rf /var/lib/apt/lists/*
RUN useradd -r -u 10001 -m aiws-infer
COPY --chmod=755 llama-server /usr/local/bin/llama-server
COPY --chmod=444 model.gguf /opt/aiws/model.gguf
COPY --chmod=444 inference_smoke.py /opt/aiws/inference_smoke.py
USER 10001
ENV HOME=/tmp
CMD ["python3","/opt/aiws/inference_smoke.py"]
