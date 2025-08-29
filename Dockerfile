FROM python:3.10-slim

WORKDIR /app

# System deps (optional but helpful)
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

COPY operator/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY operator/ /app/

CMD ["kopf", "run", "--standalone", "/app/operator.py"]
 
