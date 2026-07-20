import os
import logging
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import requests
import re
from dateutil import parser as date_parser

from dotenv import load_dotenv  # новая строка

# Загружаем переменные из .env файла
load_dotenv() 

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Безопасное получение настроек из переменных окружения
KAITAN_TOKEN = os.getenv('KAITAN_TOKEN')
BOARD_ID = os.getenv('BOARD_ID')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
SECRET_TOKEN = os.getenv('WEBHOOK_SECRET')

def parse_date_from_text(text):
    """Парсит дату из текста (например, «завтра», «в пятницу»)"""
    try:
        today = datetime.now().date()
        if 'завтра' in text.lower():
            return (today + timedelta(days=1)).isoformat()
        elif 'послезавтра' in text.lower():
            return (today + timedelta(days=2)).isoformat()
        else:
            # Пытаемся распарсить дату стандартными средствами
            parsed_date = date_parser.parse(text, fuzzy=True)
            if parsed_date.date() != today:
                return parsed_date.date().isoformat()
    except:
        return None
    return None

def send_telegram_notification(message):
    """Отправляет сообщение в чат Telegram через бота с обработкой ошибок"""
    url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info("Уведомление успешно отправлено в Telegram")
            return True
        else:
            logger.error(f"Ошибка отправки в Telegram: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"Исключение при отправке в Telegram: {e}")
        return False

@app.route('/kaiten-task', methods=['POST'])
def create_kaiten_task():
    # Проверка секретного токена для безопасности
    if request.headers.get('X-Secret-Token') != SECRET_TOKEN:
        logger.warning("Попытка несанкционированного доступа")
        return jsonify({'status': 'error', 'message': 'Unauthorized'}), 401

    data = request.json
    command_text = data.get('text', '').strip()

    if not command_text:
        error_msg = "Пустая команда получена"
        logger.error(error_msg)
        send_telegram_notification(f"❌ {error_msg}")
        return jsonify({'status': 'error', 'message': error_msg}), 400

    logger.info(f"Получена команда: {command_text}")

    # Парсинг текста команды
    match = re.search(r'(.*?)\s*(?:до|к|в)\s*(.*)', command_text, re.IGNORECASE)
    if match:
        task_name = match.group(1).strip()
        date_text = match.group(2).strip()
        due_date = parse_date_from_text(date_text)
    else:
        task_name = command_text
        due_date = None

    # Создание задачи в Kaiten
    headers = {
        'X-API-Key': KAITAN_TOKEN,
        'Content-Type': 'application/json'
    }
    payload = {
        'name': task_name,
        'board_id': BOARD_ID
    }
    if due_date:
        payload['due_date'] = due_date

    try:
        response = requests.post(
            'https://kaiten.ru/api/v1/cards',
            headers=headers,
            json=payload,
            timeout=15
        )

        if response.status_code == 201:
            # Формируем текст уведомления
            notification_text = f"✅ *Задача создана в Kaiten*\n\n"
            notification_text += f"📝 *Название:* {task_name}\n"

            if due_date:
                notification_text += f"📅 *Срок:* {due_date}\n"

            notification_text += f"\n🔗 *Доска:* {BOARD_ID}"

            # Отправляем уведомление в Telegram
            if send_telegram_notification(notification_text):
                logger.info(f"Задача создана: {task_name}")
                return jsonify({
                    'status': 'success',
                    'message': 'Задача создана и уведомление отправлено в Telegram!',
                    'task_name': task_name,
            'due_date': due_date
        })
            else:
                # Даже если уведомление не ушло, задача создана
                logger.warning("Задача создана, но уведомление в Telegram не отправлено")
                return jsonify({
            'status': 'partial_success',
            'message': 'Задача создана, но уведомление не отправлено',
            'task_name': task_name
        })
        else:
            error_msg = f"❌ Ошибка создания задачи в Kaiten: {response.status_code}"
            logger.error(error_msg)
            send_telegram_notification(error_msg)
            return jsonify({'status': 'error', 'message': error_msg, 'kaiten_response': response.text}), 500
    except requests.exceptions.RequestException as e:
        error_msg = f"❌ Ошибка подключения к Kaiten: {e}"
        logger.error(error_msg)
        send_telegram_notification(error_msg)
        return jsonify({'status': 'error', 'message': error_msg}), 503
    except Exception as e:
        error_msg = f"❌ Неожиданная ошибка: {e}"
        logger.critical(error_msg)
        send_telegram_notification(error_msg)
        return jsonify({'status': 'error', 'message': error_msg}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Эндпоинт для проверки работоспособности сервиса"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})


if __name__ == '__main__':
    # Проверка обязательных переменных окружения
    required_vars = ['KAITAN_TOKEN', 'BOARD_ID', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'WEBHOOK_SECRET']
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        logger.critical(f"Отсутствуют обязательные переменные окружения: {missing_vars}")
        exit(1)

    app.run(host='0.0.0.0', port=5000)