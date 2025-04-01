# BOT HR con Telegram para fichaje basado en Playwright

Este proyecto utiliza [Playwright](https://playwright.dev/) para realizar un fichaje automático en un sistema determinado. El contenedor Docker basado en la imagen oficial de Playwright facilita la ejecución del script de fichaje.

## Requisitos

- [Docker](https://www.docker.com/) instalado en el sistema.

## Estructura del Proyecto

```
/app
|-- fichaje.py         # Script principal de fichaje
|-- requirements.txt   # Dependencias de Python
|-- Dockerfile         # Archivo para construir la imagen Docker
```

## Instalación y Uso

### Construir la Imagen Docker
Ejecuta el siguiente comando para construir la imagen Docker:

```sh
docker build -t fichaje-bot .
```

### Ejecutar el Contenedor
Para ejecutar el contenedor con el script de fichaje:

```sh
docker run --rm fichaje-bot
```

### Variables de Entorno
Es necesario configurar un .env con las siguientes variables de entorno:

```sh
USERNAME=
PASSWORD=
LATITUDE=
LONGITUDE=
BOT_TOKEN=
CHAT_ID=
```

## Dependencias
Las dependencias del proyecto están en `requirements.txt`. Asegúrte de incluir cualquier librería adicional que `fichaje.py` requiera.

## Notas Adicionales
- Para depuración, puedes acceder al contenedor de forma interactiva ejecutando:
  
  ```sh
  docker run --rm -it fichaje-bot /bin/bash
  ```

- Si necesitas actualizar las dependencias o modificar el script, reconstruye la imagen tras hacer cambios:
  
  ```sh
  docker build --no-cache -t fichaje-bot .
  ```

## Licencia
Este proyecto se distribuye bajo la licencia MIT.

