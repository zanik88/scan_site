FROM python:3.10-slim

WORKDIR /app

# Установка системных зависимостей (если требуются для сборки)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код приложения
COPY . .

# Создаем папки для базы и отчетов
RUN mkdir -p generated_reports

# Открываем порт для приложения
EXPOSE 8000

# Команда запуска через uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]