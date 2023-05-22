import logging
import os
import sys
import time
from http import HTTPStatus
from json import JSONDecodeError

import requests
import telegram
from dotenv import load_dotenv

from exceptions import FailedRequest, NoHomework

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s',
)
handler.setFormatter(formatter)
logger.addHandler(handler)


def check_tokens() -> None:
    """Проверка доступности переменных окружения."""
    logger.debug(check_tokens.__doc__)
    REQUIRED_ENV_VARS = {
        'PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID',
    }
    try:
        for variable in REQUIRED_ENV_VARS:
            if not globals().get(f'{variable}'):
                raise EnvironmentError(
                    'Отсутствует обязательная переменная окружения: '
                    f'{variable}'
                )
    except EnvironmentError as error:
        logger.critical(f'{error}.\n>>> Программа принудительно остановлена.')
        exit(1)
    logger.info('Переменные доступны. OK')


def send_message(bot, message):
    """Отправка сообщения в Telegram чат."""
    logger.debug(send_message.__doc__)
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(f'Бот отправил сообщение:\n>>> {message}')
        return True
    except Exception as error:
        logger.error(f'Сообщение отправить не удалось:\n>>> {error}')


def get_api_answer(timestamp):
    """Запрос к эндпоинту API-сервиса."""
    logger.debug(get_api_answer.__doc__)
    payload = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
    except requests.RequestException:
        raise ConnectionError(
            f'Эндпоинт [{ENDPOINT}] недоступен.\n'
            '>>> Нет соединения с сервером.'
        )
    if response.status_code != HTTPStatus.OK:
        raise FailedRequest(
            f'Эндпоинт [{ENDPOINT}] недоступен.\n'
            f'>>> Код ответа API: [{response.status_code}].'
        )
    try:
        response = response.json()
    except JSONDecodeError as error:
        raise JSONDecodeError(
            'Ответ не соответствует ожидаемому типу данных: <type no JSON>\n'
            f'>>> {error.msg}',
            error.doc,
            error.pos,
        )
    logger.info('Эндпоинт доступен. OK')
    return response


def check_response(response):
    """Проверка ответа API на соответствие документации."""
    logger.debug(check_response.__doc__)
    if not isinstance(response, dict):
        raise TypeError(
            'Ответ не соответствует ожидаемому типу данных: <type no dict>'
        )
    if 'homeworks' not in response:
        raise KeyError('Ответ не содержит ключа "homeworks"')
    if not isinstance(response['homeworks'], list):
        raise TypeError(
            'Ответ не соответствует ожидаемому типу данных: <type no list>'
        )
    if len(response['homeworks']) == 0:
        raise NoHomework('Список домашних работ пуст.')
    logger.info('Ответ API соответствует документации. OK')
    return response['homeworks'][0]


def parse_status(homework) -> str:
    """Извлечение статуса домашней работы."""
    logger.debug(parse_status.__doc__)
    try:
        status = homework['status']
    except KeyError:
        raise KeyError('Нет ключа "status"')
    try:
        homework_name = homework['homework_name']
    except KeyError:
        raise KeyError('Нет ключа "homework_name"')
    try:
        verdict = HOMEWORK_VERDICTS[f'{status}']
    except KeyError:
        raise KeyError(f'Неожиданный статус домашней работы: {status}')
    logger.info('Статус извлечен. OK')
    return (
        f'Изменился статус проверки работы "{homework_name}".\n'
        f'>>> {verdict}'
    )


def main():
    """Основная логика работы бота."""
    logger.info('Запуск программы Бот-ассистент.')

    check_tokens()

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_msg = {}

    while True:
        try:
            response = get_api_answer(timestamp)
            homework = check_response(response)
            message = parse_status(homework)
            if message == last_msg.get('message'):
                logger.info('Обновлений нет!')
                continue
            if send_message(bot, message):
                last_msg['message'] = message

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if message == last_msg.get('error'):
                continue
            if send_message(bot, message):
                last_msg['error'] = message

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
