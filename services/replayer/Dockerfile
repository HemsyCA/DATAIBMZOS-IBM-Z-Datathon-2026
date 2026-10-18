FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir requests pandas
COPY services/replayer/main.py .
CMD ["python", "main.py"]
