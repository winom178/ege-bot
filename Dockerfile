# Используем официальный образ Python 3.11
FROM python:3.11-slim

# Устанавливаем системные зависимости:
# - tesseract-ocr и русский языковой пакет для распознавания фото
# - шрифты (включая DejaVu) для PDF
# - необходимые библиотеки для работы Pillow и других пакетов
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-rus \
    fonts-dejavu-core \
    fonts-dejavu-extra \
    gcc \
    g++ \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все остальные файлы проекта в контейнер
COPY . .

# Указываем порт, который будет слушать приложение (Render использует порт 10000 по умолчанию)
EXPOSE 10000

# Команда для запуска бота
CMD ["python", "bot.py"]
