"""Взаимодействие с окном Viber.

Публичный API класса — 7 действий с Viber:

    1. has_new_messages()   — проверить наличие новых сообщений
    2. get_chat_list()      — получить список чатов на экране      (заглушка)
    3. scroll_chats()       — прокрутить список чатов
    4. scroll_messages()    — прокрутить ленту сообщений
    5. get_messages_text()  — получить тексты сообщений            (заглушка)
    6. send_message()       — отправить текст в открытый чат
    7. click_chat()         — кликнуть по нужному чату             (заглушка)

Низкоуровневые утилиты (снимки экрана, поиск цвета, скролл, клики, ввод,
поиск окна) — в модуле ocr_screen; координаты, цвета и задержки — в viber_config.
"""

import time
from typing import List, Tuple

import viber_config as cfg
from ocr_screen import SCROLL_DOWN,SCROLL_UP,ScreenAnalyzer


class ViberWindowError(RuntimeError):
    """Базовая ошибка взаимодействия с окном Viber."""


class ViberWindowNotFoundError(ViberWindowError):
    """Окно Viber не найдено."""


class ViberWindow:
    """Высокоуровневые действия с окном Viber."""

    
    def __init__(self, title: str = cfg.WINDOW_TITLE) -> None:
        self.title = title

    # ------------------------------------------------------------------
    # Приватные помощники (геометрия и фокус окна)
    # ------------------------------------------------------------------

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
        elif not window.isActive:
            window.activate()
            time.sleep(cfg.WINDOW_ACTIVATE_DELAY)
        return window

    def _activate(self) -> None:
        """Вывести окно Viber на передний план."""
        window = self._window()
        ScreenAnalyzer.activate_window(window)
        time.sleep(cfg.WINDOW_ACTIVATE_DELAY)

    def _window_rect(self) -> Tuple[int, int, int, int]:
        """Прямоугольник окна: (left, top, width, height) в координатах экрана."""
        window = self._window()
        return window.left, window.top, window.width, window.height

    def _absolute_zone(self, zone: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
        """Перевести зону из координат окна в координаты экрана."""
        left, top, _, _ = self._window_rect()
        x, y, width, height = zone
        return left + x, top + 30 + y, width, height

    def _abs_pnt(self, point: Tuple[int, int]) -> Tuple[int, int]:
        """Перевести точку из координат окна в координаты экрана."""
        left, top, _, _ = self._window_rect()
        return left + point[0], top + 30 + point[1]

    def _scroll(self, point: Tuple[int, int], direction: int, amount: int) -> None:
        """Прокрутить колёсиком над точкой окна и дать списку перерисоваться."""
        x, y = self._abs_pnt(point)
        ScreenAnalyzer.scroll_at(x, y, direction, amount)
        time.sleep(cfg.SCROLL_SETTLE_DELAY)

    # ------------------------------------------------------------------
    # 1. Новые сообщения
    # ------------------------------------------------------------------

    def has_new_messages(self) -> bool:
        """Проверить, есть ли новые сообщения (пиксели цвета кружка в зоне).
        Прокручивает наверх список чатов, проверяет наличие кружка"""

        self.scroll_chats_to_up()
            
        x, y, width, height = self._absolute_zone(cfg.NEW_MESSAGES_ZONE)
        return ScreenAnalyzer.has_color_in_region(
            x,
            y,
            width,
            height,
            cfg.NEW_MESSAGE_COLOR,
            cfg.NEW_MESSAGE_COLOR_TOLERANCE,
            cfg.NEW_MESSAGE_MIN_PIXELS,
        )

    # ------------------------------------------------------------------
    # 2. Список чатов
    # ------------------------------------------------------------------

    def get_chat_list(self) -> List[str]:
        """Получить список чатов на текущем экране.

        Учесть в списки чатов поле с днюхами, поле с рекламой
        Высота строчки чата - 72 пикс
        вначале списка чатов может быть поле с днюхами(не обязательно), потом список чатов, потом реклама(тоже не обязательно)
        поле с днюхами 40 px, цвет 115, 96, 242

        """
        #проверить, что нет поля с днюхой. Если есть, то закрыть его, подождать полескунды, и потом уже сканировать список чатов
        x, y, width, height = self._absolute_zone(cfg.CHAT_LIST_HOLIDAY_FIELD)
        if ScreenAnalyzer.has_color_in_region(
            x, y, width, 40,
            cfg.COLOR_CHAT_LIST_HOLIDAY_FIELD,
            cfg.DEFAULT_COLOR_TOLERANCE,
            20,
        ):
            #кликнуть по кнопке закрытия поля с днюхой (кнопка крестик в правом верхнем углу поля)
            print("Закрываем поле с днюхой")    #TODO: ложные сработки бывают, доработать
            ScreenAnalyzer.click_in_place(*self._abs_pnt(cfg.BUTTON_CLOSE_HOLIDAY_FIELD))
            time.sleep(cfg.CLICK_DEFAULT_DELAY)

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
            chat_list.append(chat_name)

            # TODO: если имя чата пустое, то открыть чат, и скопировать имя чата через правое меню и вставить из буфера. 
            #           Обязательно проверить, не прочитали ли случайно новые сообщения!!!
            # TODO: тут позже вставть проверку на рекламу
            cury += cfg.CHAT_RECORD_HEIGHT  # переходим к следующей строке чата
        return chat_list

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
                self._scroll(cfg.CHATS_SCROLL_POINT, SCROLL_UP, cfg.SCROLL_AMOUNT)
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
        #TODO: очень плохо работает, совсем мало прокручивает.
        self._scroll(cfg.MESSAGES_SCROLL_POINT, direction, amount)

    # ------------------------------------------------------------------
    # 5. Текст сообщений (заглушка)
    # ------------------------------------------------------------------

    def get_messages_text(self) -> List[str]:
        """Получить тексты сообщений открытого чата.

        Заглушка: алгоритм распознавания будет реализован позже.
        """
        return []  # TODO: реализовать получение текста сообщений

    # ------------------------------------------------------------------
    # 6. Отправка сообщения
    # ------------------------------------------------------------------

    def send_message(self, text: str) -> None:
        """Отправить текст в поле ввода открытого чата.

        Клик по полю ввода -> ввод текста (буфер обмена + Ctrl+V) -> Enter.
        """
        if not text:
            return

        self._activate()

        # Клик по полю ввода, чтобы перевести фокус в него
        x, y, width, height = self._absolute_zone(cfg.MESSAGE_INPUT_ZONE)
        ScreenAnalyzer.click_in_place(x + width // 2, y + height // 2)
        time.sleep(cfg.CLICK_SETTLE_DELAY)

        ScreenAnalyzer.type_text_clipboard(text)
        time.sleep(cfg.SEND_KEY_DELAY)

        ScreenAnalyzer.press_key("enter")

    # ------------------------------------------------------------------
    # 7. Клик по чату (заглушка)
    # ------------------------------------------------------------------

    def click_chat(self, chat: str) -> bool:
        """Кликнуть по чату из списка, чтобы открыть его.

        Заглушка: алгоритм поиска чата будет реализован позже.
        """
        return False  # TODO: реализовать поиск и клик по нужному чату


if __name__ == "__main__":
    # Быстрая проверка: окно найдено, зона новых сообщений работает
    time.sleep(20)
    viber = ViberWindow()
    print(f"Окно '{viber.title}': {viber._window_rect()}")
    print(f"Зона новых сообщений (экран): {viber._absolute_zone(cfg.NEW_MESSAGES_ZONE)}")
    print(f"Есть новые сообщения: {viber.has_new_messages()}")
    print(f"Чаты: {viber.get_chat_list()}")
    print(f"Сообщения (заглушка): {viber.get_messages_text()}")
