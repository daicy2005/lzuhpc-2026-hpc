FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential clang cmake ninja-build python3 git ca-certificates nlohmann-json3-dev \
    && apt-get clean
