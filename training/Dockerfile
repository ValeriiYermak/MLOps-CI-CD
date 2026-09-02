FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY train_and_push.py .

ENTRYPOINT ["python", "train_and_push.py"]