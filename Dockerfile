FROM python:3.13-alpine

# Dependências
RUN apk update && apk add --no-cache \
                        gcc \
                        libc-dev \
                        libffi-dev \
                        linux-headers \
                        musl-dev \
                        mysql-dev \
                        postgresql-dev \
                        vim \
                        curl \
                        build-base

# Instalação do Poetry
ENV POETRY_VERSION=1.8.2
RUN curl -sSL https://install.python-poetry.org | python3 - && \
    ln -s /root/.local/bin/poetry /usr/local/bin/poetry

WORKDIR /myfinance
COPY myfinance /myfinance

# Instala as dependências do projeto
RUN poetry config virtualenvs.create false \
  && poetry install --no-interaction --no-ansi

CMD ["sh"]
