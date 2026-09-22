FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY equipment_sim.py host_bridge.py ./
ENV PYTHONUNBUFFERED=1
CMD ["python", "equipment_sim.py"]
