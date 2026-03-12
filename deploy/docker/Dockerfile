FROM python:3.11-slim

# Set Moscow timezone
RUN ln -snf /usr/share/zoneinfo/Europe/Moscow /etc/localtime && echo Europe/Moscow > /etc/timezone

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN pip3 install --no-cache-dir .

EXPOSE 5000
CMD ["telegram-log-service"]
