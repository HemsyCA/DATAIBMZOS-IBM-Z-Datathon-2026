FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn xgboost numpy pandas requests
COPY services/scorer/main.py .
COPY security ./security
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
