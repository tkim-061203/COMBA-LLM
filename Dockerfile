# syntax=docker/dockerfile:1
FROM verilator/verilator:latest

RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y build-essential clang lld bison flex \
    libreadline-dev gawk tcl-dev libffi-dev git \
    graphviz xdot pkg-config python3 libboost-system-dev \
    libboost-python-dev libboost-filesystem-dev zlib1g-dev

WORKDIR /tmp

RUN git clone --recurse-submodules https://github.com/YosysHQ/yosys.git \
    && cd yosys \
    && make \
    && make install

ENV PATH /opt/yosys/bin:$PATH

RUN useradd -m yosys
USER yosys

WORKDIR /work

ENTRYPOINT [ "/bin/bash" ]