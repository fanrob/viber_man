"""Взаимодействие с окном Viber.

Публичный API — функции, необходимые для алгоритма бота (см. main.py):

    Окно:
        activate()                   — развернуть окно на передний план (вызов при старте)

    1. has_new_messages()            — есть ли кружок новых сообщений
       find_unread_chat_positions()  — позиции строк чатов с кружком
    2. get_chat_list()               — чаты, видимые на экране (имя + позиция строки)
       find_chat()                   — найти чат по имени среди видимых
       get_chat_name()               — имя чата по позиции строки (правый клик -> Копировать)
       get_opened_chat_name()        — имя открытого чата
    3. scroll_chats()                — прокрутить список чатов
    4. scroll_messages()             — прокрутить ленту сообщений
       scroll_messages_to_bottom()   — нажать кнопку «вниз до конца»
    5. get_messages()                — сообщения открытого чата (текст + время)
    6. send_message()                — отправить текст
       type_message()                — ввести текст без отправки (для проверки)
       submit_message()              — нажать Enter (отправить)
       get_input_text()              — прочитать набранный текст (проверка)
       is_message_sent()             — проверить, что сообщение дошло (TODO алгоритма)
    7. click_chat() / click_chat_at() — кликнуть по чату (по имени / по позиции)

Низкоуровневые утилиты (снимки экрана, поиск цвета, скролл, клики, ввод, буфер
обмена) — в модуле ocr_screen; координаты, цвета и задержки — в viber_config.
"""

import time
from datetime import datetime
from typing import List, NamedTuple, Tuple

import pyautogui

import viber_config as cfg
from ocr_screen import ScreenAnalyzer
from viber_config import CHAT_LIST_HOLIDAY_FIELD, Point

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ViberWindowError(RuntimeError):
    """Базовая ошибка взаимодействия с окном Viber."""


class ViberWindowNotFoundError(ViberWindowError):
    """Окно Viber не найдено."""


class ChatEntry(NamedTuple):
    """Чат в списке на экране."""

    name: str        # имя чата (распознано или скопировано)
    position: Point  # центр строки чата в координатах окна


class Message(NamedTuple):
    """Сообщение в ленте открытого чата."""

    text: str                # текст сообщения
    time: datetime | None    # разобранное время (None, если не распознано)


class ViberWindow:
    """Высокоуровневые действия с окном Viber."""

    # Направления скролла (дублируются из конфига для удобства вызова)
    SCROLL_UP = cfg.SCROLL_UP
    SCROLL_DOWN = cfg.SCROLL_DOWN

    def __init__(self, title: str = cfg.WINDOW_TITLE) -> None:
        self.title = title

    # ------------------------------------------------------------------
    # Окно
    # ------------------------------------------------------------------

    def activate(self) -> None:
        """Вывести окно Viber на передний план (развернув, если свёрнуто)."""
        window = self._window()
        ScreenAnalyzer.activate_window(window)
        time.sleep(cfg.WINDOW_ACTIVATE_DELAY)

    def _window(self):
        """Найти окно Viber (и развернуть, если свёрнуто)."""
        window = ScreenAnalyzer.find_window(self.title)
        if window is None:
            raise ViberWindowNotFoundError(
                f"Окно '{self.title}' не найдено. Откройте Viber или измените "
                "cfg.WINDOW_TITLE в viber_config.py"
            )
        if window.isMinimized:
            window.restore()
            time.sleep(cfg.WINDOW_ACTIVATE_DELAY)
        return window

    def _window_rect(self) -> Tuple[int, int, int, int]:
        """Прямоугольник окна: (left, top, width, height) в координатах экрана."""
        window = self._window()
        return window.left, window.top, window.width, window.height

    def _absolute_zone(self, zone: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
        """Перевести зону из координат окна в координаты экрана."""
        left, top, _, _ = self._window_rect()
        x, y, width, height = zone
        #корректировка в 30 для строки заголовка окна
        return left + x, top + 30 + y, width, height

    def _abs_pnt(self, point: Point) -> Point:
        """Перевести точку из координат окна в координаты экрана."""
        left, top, _, _ = self._window_rect()
        #корректировка в 30 для строки заголовка окна
        return left + point[0], top + 30 + point[1]

    def close_holiday(self):
        #проверяем что есть полоска с днюхой и кликаем по закрытию
        #TODO: реализовать
        color_matches = ScreenAnalyzer.has_color_in_region(
            *self._absolute_zone(CHAT_LIST_HOLIDAY_FIELD),
            cfg.HOLIDAY_COLOR,
            cfg.HOLIDAY_COLOR_TOLERANCE,
            cfg.HOLIDAY_MIN_PIXELS
        )
        if color_matches:
            x, y = self._abs_pnt(cfg.BUTTON_CLOSE_HOLIDAY_FIELD)
            ScreenAnalyzer.click_in_place(x, y)
            time.sleep(cfg.CLICK_SETTLE_DELAY)
        
    # ------------------------------------------------------------------
    # 1. Новые сообщения
    # ------------------------------------------------------------------

    def has_new_messages(self) -> bool:
        """Проверить, есть ли новые сообщения (пиксели цвета бейджа в зоне)."""
        x, y, width, height = self._absolute_zone(cfg.FULL_NEW_MESSAGES_ZONE)
        return ScreenAnalyzer.has_color_in_region(
            x,
            y,
            width,
            height,
            cfg.NEW_MESSAGE_COLOR,
            cfg.NEW_MESSAGE_COLOR_TOLERANCE,
            cfg.NEW_MESSAGE_MIN_PIXELS,
        )

    def check_has_new_messages(self, position: Point) -> bool:
        """Проверить, есть ли новые сообщения в указанной зоне."""
        x, y, width, height = self._absolute_zone((position[0], position[1], cfg.NEW_MESSAGE_ZONE_WIDTH, cfg.NEW_MESSAGE_ZONE_HEIGHT))
        return ScreenAnalyzer.has_color_in_region(
            x,
            y,
            width,
            height,
            cfg.NEW_MESSAGE_COLOR,
            cfg.NEW_MESSAGE_COLOR_TOLERANCE,
            cfg.NEW_MESSAGE_MIN_PIXELS,
        )

    def find_unread_chat_positions(self) -> List[Point]:
        """Найти чаты с кружком новых сообщений на текущем экране.

        Returns:
            Центры строк чатов с кружком (координаты окна), сверху вниз.
            Пустой список, если кружков на экране нет.
        """
        return []  # TODO: сканировать CHAT_LIST_ZONE на цвет кружка, группировать по строкам

    # ------------------------------------------------------------------
    # 2. Список чатов
    # ------------------------------------------------------------------

    def get_chat_list(self) -> List[str]:
        """Получить список чатов на текущем экране.
        Возвращает список имён чатов (распознанных или скопированных), сверху вниз.
        Массив чатов с полями name и has_new_message (наличие кружка новых сообщений).

        Учесть в списки чатов поле с днюхами, поле с рекламой
        Высота строчки чата - 72 пикс
        вначале списка чатов может быть поле с днюхами(не обязательно), потом список чатов, потом реклама(тоже не обязательно)
        поле с днюхами 40 px, цвет 115, 96, 242

        """
        self.close_holiday()  #закрыть поле с днюхами, если оно есть

        #теперь список чатов. Высота строки чата - 72 px. Сканируем список чатов сверху вниз, пока не дойдём до конца зоны списка чатов
        cury = 0
        chat_list = []
        while cury < cfg.CHAT_LIST_ZONE[3]:
            # 1. получаем зону с названием чата
            # 2. получаем число новых сообщений в чате (если есть)

            # распознать текст в зоне названия чата (OCR)
            chat_name = ScreenAnalyzer.get_text_in_region(
                *self._absolute_zone((cfg.CHAT_LIST_ZONE[0]+cfg.CHAT_HEADER_COORD[0], 
                                      cfg.CHAT_LIST_ZONE[1] + cury + cfg.CHAT_HEADER_COORD[1], 
                                      cfg.CHAT_HEADER_COORD[2], 
                                      cfg.CHAT_HEADER_COORD[3]))
            )
            has_new_message = self.check_has_new_messages((cfg.CHAT_LIST_ZONE[0]+cfg.CHAT_HEADER_COORD[0], 
                                                           cfg.CHAT_LIST_ZONE[1] + cury + cfg.CHAT_HEADER_COORD[1]))
            chat_list.append(ChatEntry(name=chat_name, has_new_message=has_new_message))

            # TODO: если имя чата пустое, то открыть чат, и скопировать имя чата через правое меню и вставить из буфера. 
            #           Обязательно проверить, не прочитали ли случайно новые сообщения!!!
            # TODO: тут позже вставть проверку на рекламу
            cury += cfg.CHAT_RECORD_HEIGHT  # переходим к следующей строке чата
        return chat_list

    def find_chat(self, name: str) -> ChatEntry | None:
        """Найти чат с указанным именем среди видимых на экране.

        Args:
            name: имя чата (точное или частичное совпадение — решить при реализации).

        Returns:
            Найденный чат или None, если на экране его нет (тогда нужно
            прокрутить список и повторить поиск).
        """
        return None  # TODO: перебрать get_chat_list() и сравнить имена

    def get_chat_name(self, position: Point) -> str:
        """Имя чата по позиции его строки: правый клик -> «Копировать» -> буфер.

        Args:
            position: центр строки чата в координатах окна
                (из find_unread_chat_positions() или get_chat_list()).

        Returns:
            Имя чата или "", если скопировать не удалось.
        """
        return ""  # TODO: правый клик -> пункт cfg.COPY_MENU_ITEM -> чтение буфера

    def get_opened_chat_name(self) -> str:
        """Имя открытого чата (заголовок переписки).

        Используется в обходном пути «открыть каждый чат и проверить имя».

        Returns:
            Имя открытого чата или "", если получить не удалось.
        """
        return ""  # TODO: копирование из заголовка переписки (правый клик / OCR)

    # ------------------------------------------------------------------
    # 3. Скролл списка чатов
    # ------------------------------------------------------------------

    def scroll_chats(self, direction: int, amount: int = cfg.SCROLL_AMOUNT) -> None:
        """Прокрутить список чатов вверх/вниз (колёсико над списком чатов)."""
        self._scroll(cfg.CHATS_SCROLL_POINT, direction, amount)

    def scroll_chats_to_up(self):
        #проверить, что кнопка вверх списка чатов видна (т.е. список не прокручен до верха)
        x, y, width, height = self._absolute_zone(cfg.BUTTON_UP_ZONE)
        if not ScreenAnalyzer.has_color_in_region(
            x, y, width, height,
            cfg.BUTTON_UP_COLOR,
            cfg.NEW_MESSAGE_COLOR_TOLERANCE,
            cfg.BUTTON_UP_MIN_PIXELS,
        ):
            for _ in range(5):  # если кнопки вверх нет, то просто прокрутим вверх немного на всякий случай
                self._scroll(cfg.CHATS_SCROLL_POINT, cfg.SCROLL_UP, cfg.SCROLL_AMOUNT)
                time.sleep(cfg.SCROLL_SETTLE_DELAY)
        else:
            #нажать мышкой на кнопку вверх списка чатов, чтобы прокрутить наверх
            x, y = self._abs_pnt(cfg.BUTTON_UP)
            ScreenAnalyzer.click_in_place(x, y)

        time.sleep(cfg.SCROLL_SETTLE_DELAY)

    # ------------------------------------------------------------------
    # 4. Скролл ленты сообщений
    # ------------------------------------------------------------------

    def scroll_messages(self, direction: int, amount: int = cfg.SCROLL_AMOUNT) -> None:
        """Прокрутить ленту сообщений вверх/вниз (колёсико над лентой)."""
        self._scroll(cfg.MESSAGES_SCROLL_POINT, direction, amount)

    def scroll_messages_to_bottom(self) -> None:
        """Поставить ленту в самый конец нажатием кнопки «вниз до конца»."""
        pass  # TODO: клик по кнопке (её зона/цвет — в viber_config)

    # ------------------------------------------------------------------
    # 5. Текст сообщений
    # ------------------------------------------------------------------

    def get_messages(self, since: datetime | None = None) -> List[Message]:
        """Сообщения открытого чата, от старых к новым.

        Чтение идёт снизу вверх, пока не будет достигнуто уже известное
        сообщение (граница `since`) — чтобы не читать обработанное ранее.

        Args:
            since: если задан — возвращаются только сообщения новее этого
                времени; None — все видимые сообщения.

        Returns:
            Список сообщений (text + time), от старых к новым.
            Заглушка: алгоритм распознавания будет реализован позже.
        """
        return []  # TODO: OCR ленты снизу вверх до границы since

    # ------------------------------------------------------------------
    # 6. Отправка сообщения
    # ------------------------------------------------------------------

    def send_message(self, text: str) -> None:
        """Отправить текст в поле ввода открытого чата.

        Клик по полю ввода -> ввод текста (буфер обмена + Ctrl+V) -> Enter.
        """
        if not text:
            return

        self.activate()

        # Клик по полю ввода, чтобы перевести фокус в него
        x, y, width, height = self._absolute_zone(cfg.MESSAGE_INPUT_ZONE)
        ScreenAnalyzer.click_in_place(x + width // 2, y + height // 2)
        time.sleep(cfg.CLICK_SETTLE_DELAY)

        ScreenAnalyzer.type_text_clipboard(text)
        time.sleep(cfg.SEND_KEY_DELAY)

        ScreenAnalyzer.press_key(cfg.SUBMIT_KEY)

    def type_message(self, text: str) -> None:
        """Ввести текст в поле ввода, НЕ отправляя его.

        Нужен для проверки (get_input_text) перед submit_message().

        Заглушка: после реализации send_message() можно собирать из
        type_message() + submit_message(), чтобы не дублировать код.
        """
        pass  # TODO: клик по полю ввода + type_text_clipboard()

    def submit_message(self) -> None:
        """Отправить то, что набрано в поле ввода (Enter)."""
        pass  # TODO: press_key(cfg.SUBMIT_KEY)

    def get_input_text(self) -> str:
        """Прочитать текст, набранный в поле ввода (Ctrl+A -> Ctrl+C -> буфер).

        Внимание: буфер обмена затирается — серверный текст нужно сохранить
        заранее (до type_message).

        Returns:
            Набранный текст или "", если прочитать не удалось.
        """
        return ""  # TODO: выделить всё в поле ввода и скопировать

    def is_message_sent(self, text: str) -> bool:
        """Проверить, что сообщение с таким текстом появилось в ленте.

        TODO из алгоритма: проверка статуса отправленного сообщения.

        Returns:
            True, если последнее сообщение в ленте совпадает с `text`.
        """
        return False  # TODO: прочитать последнее сообщение ленты и сравнить

    # ------------------------------------------------------------------
    # 7. Клик по чату
    # ------------------------------------------------------------------

    def click_chat(self, chat: str) -> bool:
        """Кликнуть по чату с указанным именем, чтобы открыть его.

        Ищет только среди видимых на экране чатов (find_chat); если чата нет
        на экране — вернуть False, а вызывающий код прокрутит список и повторит.

        Returns:
            True, если чат найден и по нему кликнули.
        """
        return False  # TODO: find_chat() + клик по позиции строки

    def click_chat_at(self, position: Point) -> bool:
        """Кликнуть по строке чата в указанной позиции.

        Args:
            position: центр строки чата в координатах окна.

        Returns:
            True, если позиция внутри зоны списка чатов и клик выполнен.
        """
        return False  # TODO: проверить, что позиция внутри CHAT_LIST_ZONE, и кликнуть

    # ------------------------------------------------------------------
    # Приватные помощники
    # ------------------------------------------------------------------

    def _scroll(self, point: Point, direction: int, amount: int) -> None:
        """Прокрутить колёсиком над точкой окна и дать списку перерисоваться."""
        logger.info("Прокрутка списка чатов...")
        x, y = self._abs_pnt(point)
        ScreenAnalyzer.scroll_at(x, y, direction, amount)
        time.sleep(cfg.SCROLL_SETTLE_DELAY)


if __name__ == "__main__":
    # Быстрая проверка: окно найдено, зона новых сообщений работает
    pyautogui.FAILSAFE = False
    
    TEST = 1
    if TEST == 1:
        logger.info("Тестирование ViberWindow...")
        viber = ViberWindow()
        viber.activate()
        print(f"Окно '{viber.title}': {viber._window_rect()}")
        print(f"Есть новые сообщения: {viber.has_new_messages()}")
        print(f"Позиции непрочитанных (заглушка): {viber.find_unread_chat_positions()}")
        print(f"Чаты на экране (заглушка): {viber.get_chat_list()}")
        print(f"Сообщения (заглушка): {viber.get_messages()}")

        #тестовый цикл сканирования чатов и получения их имён
        while True:
            try:
                viber.activate()
                chat_list = viber.get_chat_list()
                print(f"Чаты на экране: {chat_list}")
                time.sleep(5)
                #прокуртить список чатов вниз
                viber.scroll_chats(ViberWindow.SCROLL_DOWN, 50)
                #сделать скрин списка чатов и сохранить в файл
                x, y, width, height = viber._absolute_zone(cfg.CHAT_LIST_ZONE)
                ScreenAnalyzer.capture_region(x, y, width, height).save(f"chat_list_{time.time()}.png")
            except: 
                pass
    