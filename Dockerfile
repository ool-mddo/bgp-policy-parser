FROM python:3.11-slim

RUN mkdir -p /bgp-policy-parser
WORKDIR /bgp-policy-parser
COPY . /bgp-policy-parser/

# install gitops for GitPython
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements_prod.txt
# enable multiple line paste in python REPL (python -i)
RUN echo "set enable-bracketed-paste off" >> ~/.inputrc
# NOTE: currently, NO entrypoint, to use only environment packing, it will be API service
