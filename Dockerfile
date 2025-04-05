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

WORKDIR /myfinance

COPY myfinance /myfinance

RUN pip install -r requirements.txt

RUN pip install gunicorn

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "myfinance.asgi:application"]
