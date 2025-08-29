# ---- Base
FROM python:3.12-slim

WORKDIR /app

# Install python deps
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . .
RUN chmod +x /app/start.sh

# Basic env
ENV PORT=7860
ENV CHAINLIT_APP_ROOT=/tmp
ENV AWS_DEFAULT_REGION=us-east-1

EXPOSE 7860
CMD ["/app/start.sh"]