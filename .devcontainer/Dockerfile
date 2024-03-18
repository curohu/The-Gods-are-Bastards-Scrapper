# FROM ubuntu:latest
FROM debian:stable-slim

# install packages
RUN apt-get update && \
    apt-get upgrade && \
    apt-get install -Vy \
    git \
    python3.11 \
    pip \
    python3.11-venv \
    vim

# create link
RUN ln -s /usr/bin/python3.11 /usr/bin/python

# Create venv and install depencancies
COPY requirements.txt /tmp/requirements.txt
RUN python -m venv /root/.pyenv && \
    echo "source /root/.pyenv/bin/activate" >> /root/.bashrc && \
    /root/.pyenv/bin/pip install -vr /tmp/requirements.txt
