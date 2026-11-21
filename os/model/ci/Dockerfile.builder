FROM debian:trixie-slim
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      ca-certificates cmake ninja-build g++ git make pkg-config libgomp1 && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY . /src/
RUN cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
      -DGGML_NATIVE=OFF -DGGML_CUDA=OFF -DLLAMA_CURL=OFF \
      -DBUILD_SHARED_LIBS=OFF && \
    cmake --build build --target llama-server --parallel 2 && \
    test -x build/bin/llama-server
