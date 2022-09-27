
import os
import time
import sys
import requests
import logging
from telegram import Bot
from telegram.error import TelegramError
from dotenv import load_dotenv


load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

logging_tokensErrorsMessage = ("Some tokens are not available in environment. "
                               "File .env expected to exist in root and "
                               "to contain PRACTICUM_TOKEN, TELEGRAM_TOKEN"
                               " and TELEGRAM_CHAT_ID")
logging_sentMessage = ("Message sent successfully: ")
logging_messageNotSent = ("Error while sending message to telegram: ")

# debug code
# PRACTICUM_TOKEN = "wrong token"

RETRY_TIME = 600
# debug retry
# RETRY_TIME = 2
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

EXPECTED_FAIL_KEYS_400 = ["code", "error"]
EXPECTED_FAIL_KEYS_401 = ["code", "message"]
EXPECTED_SUCCESS_KEYS = ['current_date', 'homeworks']


def send_message(bot: Bot, message: str):
    """Function to send messages via bot.
    Doesn't check success of delivery
    """
    bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=message
    )


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
    res = requests.get(ENDPOINT, headers=HEADERS, params=params)

    if res.status_code == 400:
        message = str(res.json().get("error", "unknown response error"))
        raise WrongAPIRequest("API request error, " + message)

    if res.status_code == 401:
        message = str(res.json().get("message", "unknown response error"))
        raise WrongAPIRequest("API request error, " + message)

    if res.status_code != 200:
        message = "unknown response error"
        raise WrongAPIRequest("API request error, " + message)

    try:
        data = res.json()
    except Exception:
        raise TypeError("response can't be decoded into json")
    return data


def check_response(response: dict):
    """Function checks type and content of API response
    and returns list of all homeworks in case of success
    (even if this list is empty). Structure of expected response is
    {'current_timestamp':int, 'homeworks':[dict]}.
    Exceptions are raised if structure doesn't suit the expected.
    """
    try:
        homeworks = response[EXPECTED_SUCCESS_KEYS[1]]

        if not isinstance(homeworks, list):
            raise TypeError(
                "API response doesn't contain list of homeworks "
                "under key 'homeworks'")

        return homeworks

    except KeyError:
        raise KeyError(f"response status code is 200 "
                       f"but it doesn't contain "
                       f"key '{EXPECTED_SUCCESS_KEYS[1]}'")


def parse_status(homework: dict):
    """Function retrievs status of homework from all information about it
    and creates string to be sent to user.
    Status and name are expected to be found in dictionary
    'homework' by keys 'status' and 'homework_name'.
    If thess keys are not in dictionary exception is raised.
    """
    try:
        homework_name = homework["homework_name"]
        homework_status = homework["status"]

        verdict = HOMEWORK_STATUSES[homework_status]

        return f'Изменился статус проверки работы "{homework_name}". {verdict}'
    except KeyError:
        raise KeyError("unkonwn status or name of the last homework")


def check_tokens():
    """Function checks if file .env exists in root and includes three tokens:
    PRACTICUM_TOKEN, TELEGRAM_TOKEN and TELEGRAM_CHAT_ID
    """
    if PRACTICUM_TOKEN and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        return True
    return False


class WrongAPIRequest(ValueError):
    """Exception for problums with API"""
    pass


def main():
    """Main instruction"""
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler(stream=sys.stdout)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    logger.info("bot started")

    if not check_tokens():
        logger.critical(logging_tokensErrorsMessage)
        raise SystemExit()

    bot = Bot(token=TELEGRAM_TOKEN)

    current_timestamp = int(time.time())
    last_error_name = ""

    while True:
        try:
            response = get_api_answer(current_timestamp)
            list_of_works = check_response(response)
            current_timestamp = response[EXPECTED_SUCCESS_KEYS[0]]
            if list_of_works:
                last_work = list_of_works.pop()
                message = parse_status(last_work)
                send_message(bot, message)
                logger.info(logging_sentMessage + message)
            else:
                logger.debug("no new homeworks or statuses")
            time.sleep(RETRY_TIME)
        except TelegramError:
            logger.error(logging_messageNotSent + message)
            current_timestamp = int(time.time())
            time.sleep(RETRY_TIME)
        except Exception as error:
            new_error_name = str(error) or "unknown error"
            logger.error(new_error_name)
            if new_error_name != last_error_name:
                message = f'Сбой в работе программы: {new_error_name}'
                try:
                    send_message(bot, message)
                    logger.info(logging_sentMessage + message)
                except TelegramError:
                    logger.error(logging_messageNotSent + message)
                last_error_name = new_error_name
            current_timestamp = int(time.time())
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
