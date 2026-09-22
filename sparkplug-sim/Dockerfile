FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sparkplug_b.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. sparkplug_b.proto

COPY sim.py .

ENV PYTHONUNBUFFERED=1
CMD ["python", "sim.py"]
