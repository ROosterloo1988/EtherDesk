FROM python:3.9-slim
WORKDIR /app
RUN apt-get update && apt-get install -y git docker.io
RUN pip install flask matrix-nio aiohttp GitPython requests
COPY . .
RUN chmod +x start.sh
CMD ["./start.sh"]
