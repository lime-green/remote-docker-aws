FROM ubuntu:focal

ENV LC_ALL C.UTF-8
ENV LANG C.UTF-8

RUN ln -fs /usr/share/zoneinfo/America/New_York /etc/localtime

RUN apt-get update && apt-get install -y \
    git \
    sudo

RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    curl \
    libbz2-dev \
    libffi-dev \
    libncurses5-dev \
    libreadline-dev \
    libssl-dev \
    libsqlite3-dev \
    libxml2-dev \
    libxmlsec1-dev \
    liblzma-dev \
    llvm \
    make \
    tk-dev \
    wget \
    xz-utils \
    zlib1g-dev

RUN adduser --disabled-password --gecos '' docker
RUN adduser docker sudo
RUN echo '%sudo ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

USER docker

ENV PYENV_ROOT /home/docker/.pyenv
ENV PATH /home/docker/.pyenv/shims:/home/docker/.pyenv/bin:$PATH

RUN git clone https://github.com/pyenv/pyenv.git /home/docker/.pyenv

COPY .python-version /tmp/
RUN cat /tmp/.python-version | xargs -n1 pyenv install -s
