FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py tempo_client.py narrative.py ./

EXPOSE 8050

CMD ["python", "app.py"]
