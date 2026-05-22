FROM mcr.microsoft.com/playwright:latest

WORKDIR /app

COPY requirements.txt .
COPY config.py .
COPY main.py .
COPY bot/ ./bot/
COPY dashboard/ ./dashboard/
COPY data/ ./data/

RUN apt-get update && apt-get install -y python3 python3-pip &&     DEBIAN_FRONTEND=noninteractive TZ="Europe/Madrid" apt-get install -y tzdata

ENV TZ=Europe/Madrid
RUN ln -fs /usr/share/zoneinfo/Europe/Madrid /etc/localtime && dpkg-reconfigure -f noninteractive tzdata

RUN pip3 install --no-cache-dir -r requirements.txt
RUN python3 -m playwright install

EXPOSE 5000

CMD ["python3", "main.py"]
