FROM library/python:3.6.0

RUN pip install --upgrade \
    setuptools \
    tox \
    wheel

COPY . /app/

WORKDIR /app

RUN pip install . --process-dependency-links
ENTRYPOINT ["/usr/local/bin/nodereg"]
