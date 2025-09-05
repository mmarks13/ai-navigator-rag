# ---- Base
FROM python:3.11-slim

WORKDIR /app

# Install python deps
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .
RUN chmod +x /app/start.sh

# Basic env
ENV PORT=8000
ENV CHAINLIT_APP_ROOT=/tmp
ENV AWS_DEFAULT_REGION=us-west-2
ENV PYTHONUNBUFFERED=1

EXPOSE 8000
CMD ["/app/start.sh"]