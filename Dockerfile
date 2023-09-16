FROM python:3.11-alpine

RUN apk update && apk add --no-cache mysql-dev gcc libc-dev linux-headers musl-dev libffi-dev

WORKDIR /myfinance

COPY myfinance /myfinance

RUN pip install -r requirements.txt

RUN pip install gunicorn

COPY ./entrypoint.sh /

ENTRYPOINT [ "sh", "/entrypoint.sh" ]