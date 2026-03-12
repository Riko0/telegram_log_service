FROM python:3.11-slim

# Set Moscow timezone
RUN ln -snf /usr/share/zoneinfo/Europe/Moscow /etc/localtime && echo Europe/Moscow > /etc/timezone

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y python3 python3-pip git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY deploy/requirements.txt .

RUN pip3 install --no-cache-dir -r requirements.txt

EXPOSE 5000
ENTRYPOINT [ "./deploy/scripts/startup.sh" ]