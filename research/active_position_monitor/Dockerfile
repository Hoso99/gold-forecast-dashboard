FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY cloud_stream.py ./cloud_stream.py
ENV PYTHONUNBUFFERED=1
CMD ["python", "-u", "cloud_stream.py"]
