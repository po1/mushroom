FROM python:3.9.19-alpine

ADD mushroom /workspace/mushroom
ADD setup.py /workspace/

RUN pip install /workspace

WORKDIR /data

CMD mushroomd
