FROM python:3.11-alpine

RUN apk update && apk add --no-cache \
                        gcc \
                        libc-dev \
                        libffi-dev \
                        linux-headers \
                        musl-dev \
                        mysql-dev \
                        postgresql-dev \
                        vim

WORKDIR /myprod

COPY myprod /myprod

RUN pip install -r requirements.txt

RUN pip install gunicorn

COPY ./entrypoint.sh /

ENTRYPOINT [ "sh", "/entrypoint.sh" ]