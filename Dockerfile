# Usar la imagen base de Playwright
FROM mcr.microsoft.com/playwright:latest

# Establecer el directorio de trabajo en /app
WORKDIR /app

# Copiar el archivo `fichaje.py` explícitamente
COPY fichaje.py /app/fichaje.py

# Copiar el archivo `requirements.txt` explícitamente
COPY requirements.txt /app/requirements.txt

# Instalar python3 y pip
RUN apt-get update && apt-get install -y python3 python3-pip

# Establecer la zona horaria correctamente
RUN DEBIAN_FRONTEND=noninteractive TZ="Europe/Madrid" apt-get -y install tzdata
ENV TZ=Europe/Madrid
RUN ln -fs /usr/share/zoneinfo/Europe/Madrid /etc/localtime && dpkg-reconfigure -f noninteractive tzdata

# Instalar Playwright y sus dependencias
RUN pip3 install --no-cache-dir playwright

# Instalar las dependencias necesarias desde requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt

# Instalar los navegadores de Playwright
RUN python3 -m playwright install

# Exponer un puerto (opcional si el bot va a interactuar con un servidor)
EXPOSE 5000

# Comando para ejecutar el script
CMD ["python3", "fichaje.py"]