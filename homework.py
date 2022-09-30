
import os
import time
import sys
import requests
import logging
from errors import TelegramException, WrongAPIRequest
from telegram import Bot
from telegram.error import TelegramError
from dotenv import load_dotenv
from typing import Dict


load_dotenv()
BASE_DIR = ''

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# TELEGRAM_CHAT_ID = 17

logging.basicConfig(
    level=logging.INFO,
    format=(
        '%(asctime)s [%(levelname)s] - '
        '(%(filename)s).%(funcName)s:%(lineno)d - %(message)s'
    ),
    handlers=[
        logging.FileHandler(BASE_DIR + 'output.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

SHORTENING = 10


RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


EXPECTED_SUCCESS_KEYS = ['current_date', 'homeworks']


def send_message(bot: Bot, message: str):
    """Function to send messages via bot.
    Checks success of delivery
    """
    try:
        short_message = message[:SHORTENING]
        logging.info(
            f"Начинаем отправлять сообщение '{short_message}..'")
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message
        )
    except TelegramError as error:
        raise TelegramException(f'Ошибка отправки телеграм сообщения: {error}')
    else:
        logging.info(
            f"Сообщение '{short_message}..' успешно отправлено")


def get_api_answer(current_timestamp: int):
    """Functions returns homework API answer in json format.
    Parameters of request:
    current_timestamp is UTC moment since which all homeworks wiil be
    included in response.
    Global parameters needed:
    ENPOINT is url for request,
    HEADERS is dict of headers of request
    (at least Authorization header required)
    """
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    request_params = {'url': ENDPOINT, 'headers': HEADERS, 'params': params}
    logging.info('Начинаем подключение к эндпоинту {url}, с параметрами'
                 ' headers = {headers} ;params= {params}.'
                 .format(**request_params))
    try:
        res = requests.get(**request_params)
        if res.status_code != 200:
            raise WrongAPIRequest(
                'Ответ сервера не является успешным:'
                f' request params = {request_params};'
                f' http_code = {res.status_code};'
                f' reason = {res.reason}'
            )
    except Exception as error:
        raise ConnectionError(
            (
                'Во время подключения к эндпоинту {url} произошла'
                ' непредвиденная ошибка: {error}'
                ' headers = {headers}; params = {params};'
            ).format(
                error=error,
                **request_params
            )
        )
    else:
        logging.info(
            "Ответ API успешно получен")

    try:
        logging.info("Начинаем преобразовывать ответ API к формату JSON")
        data = res.json()
    except Exception:
        raise TypeError("Ответ нельзя преорбразовать к формату JSON")
    else:
        logging.info("Ответ API преобразовыван к формату JSON")
        return data


def check_response(response: dict):
    """Function checks type and content of API response.
    It returns list of all homeworks in case of success
    (even if this list is empty). Structure of expected response is
    {'current_timestamp':int, 'homeworks':[dict]}.
    Exceptions are raised if structure doesn't suit the expected.
    """
    if not isinstance(response, dict):
        raise TypeError(
            f"Response is expected to be 'dict' class "
            f"but it is {type(response)}")

    if any([key not in response for key in EXPECTED_SUCCESS_KEYS]):
        raise KeyError(f"В ответе API отсутствуют "
                       f"необходимые ключи {EXPECTED_SUCCESS_KEYS[0]}"
                       f"и / или {EXPECTED_SUCCESS_KEYS[1]}, "
                       f"response={response}.")

    homeworks = response[EXPECTED_SUCCESS_KEYS[1]]

    if not isinstance(homeworks, list):
        raise TypeError(
            "API response doesn't contain list of homeworks "
            "under key 'homeworks'")

    return homeworks


def parse_status(homework: dict):
    """Function retrievs status of homework from all information about it.
    and creates string to be sent to user.
    Status and name are expected to be found in dictionary
    'homework' by keys 'status' and 'homework_name' respectively.
    If thess keys are not in dictionary exception is raised.
    """
    homework_name = homework.get("homework_name")
    if not homework_name:
        raise KeyError('В домашней работе в ответе от API отсутствуют ключ'
                       f' "homework_name" : homework = {homework}.')

    homework_status = homework.get("status")
    if homework_status not in HOMEWORK_STATUSES:
        raise ValueError(f'В ответе от API пришел неизвестный статус работы,'
                         f' status={homework_status}.')

    verdict = HOMEWORK_STATUSES[homework_status]

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Function checks tokens created.
    File .env must exist in root and it must include three tokens:
    PRACTICUM_TOKEN, TELEGRAM_TOKEN and TELEGRAM_CHAT_ID
    """
    if PRACTICUM_TOKEN and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        return True
    return False


def main():
    """Main instruction."""
    logging.info("bot started")

    if not check_tokens():
        message = (
            'Отсутсвуют обязательные переменные окружения: PRACTICUM_TOKEN,'
            ' TELEGRAM_TOKEN, TELEGRAM_CHAT_ID.'
            ' Программа принудительно остановлена.')
        logging.critical(message)
        raise SystemExit(message)

    bot = Bot(token=TELEGRAM_TOKEN)

    current_timestamp = int(time.time()) - 1000000
    # last_error_name = ""
    current_report: Dict = {'name': '', 'output': ''}
    prev_report: Dict = current_report.copy()

    while True:
        try:
            response = get_api_answer(current_timestamp)
            new_list_of_works = check_response(response)
            current_timestamp = response.get(
                EXPECTED_SUCCESS_KEYS[0], current_timestamp)
            if new_list_of_works:
                logging.info(
                    f'Список новых домашних работ не пуст {new_list_of_works}')
                new_work = new_list_of_works[-1]
                current_report['name'] = new_work['homework_name']
                current_report['output'] = parse_status(new_work)
            else:
                logging.info(
                    f'За период от '
                    f'{time.ctime(current_timestamp)} '
                    f' до настоящего момента домашних работ нет.')
                current_report['output'] = ("Нет новых работ")

            if current_report != prev_report:
                message = (f"Изменился статус проверки "
                           f"работы {current_report['name']}. "
                           f"{current_report['output']}")
                # if new_list_of_works:
                logging.info(f"send message if {new_list_of_works} is True")
                if new_list_of_works:
                    send_message(bot, message)
                prev_report = current_report.copy()
            else:
                logging.info('В ответе нет новых статусов.')

        except TelegramException as error:
            message = f'Сбой в работе программы: {error}'
            logging.error(message)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            current_report['output'] = message
            logging.error(message, exc_info=True)
            if current_report != prev_report:
                send_message(bot, current_report)
                prev_report = current_report.copy()

        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
