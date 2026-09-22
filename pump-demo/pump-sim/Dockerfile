FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pump_sim.py .
ENV PYTHONUNBUFFERED=1
CMD ["python", "pump_sim.py"]
