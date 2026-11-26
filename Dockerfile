FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/data \
    CHROME_HEADLESS=true

# Cài đặt Chromium và chromedriver hệ thống để chạy Selenium ổn định trong container
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Tạo user không có quyền root để tăng cường bảo mật runtime
RUN groupadd --gid 10001 instachat \
    && useradd --uid 10001 --gid instachat --create-home instachat

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data /app/config \
    && chown -R instachat:instachat /app

USER instachat

EXPOSE 8765

CMD ["python", "start_bot.py", "--mode", "run", "--skip-install"]
