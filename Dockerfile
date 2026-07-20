FROM python:3.11-slim

WORKDIR /app

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Создаём папку для логов
RUN mkdir -p logs

# Копируем код приложения
COPY . .

# Открываем порт
EXPOSE 5000

# Запускаем приложение через gunicorn для продакшена
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]