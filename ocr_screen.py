"""Утилиты экрана: скриншоты, OCR, поиск цвета, мышь и клавиатура.

Класс ScreenAnalyzer содержит переиспользуемые утилиты:
- снимки областей экрана и OCR;
- поиск пикселей нужного цвета;
- клики, скролл колёсиком, ввод текста, нажатие клавиш;
- поиск и активация окна по заголовку.

main() — фоновый цикл: каждые 5 секунд снимает весь экран, распознавает текст
(русский + английский) и записывает его в output.txt (перезаписывая файл целиком).
"""

import time
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import mss
import pyautogui
import pyperclip
import pytesseract
from PIL import Image

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
#TESSERACT_PATH = r"C:\Users\56\AppData\Local\Tesseract-OCR\tesseract.exe"
OUTPUT_FILE = Path(__file__).with_name("output.txt")
INTERVAL = 5  # секунд
LANG = "rus+eng"
DEBUG_SAVE_REGION = True  # сохранять снимки распознаваемых областей в region_*.png (отладка OCR)

SCROLL_UP = 1
SCROLL_DOWN = -1


def _ensure_tesseract() -> None:
    """Проверить наличие Tesseract и настроить путь к нему (лениво, при OCR)."""
    if not Path(TESSERACT_PATH).exists():
        raise FileNotFoundError(
            f"Tesseract не найден по пути: {TESSERACT_PATH}\n"
            "Проверьте, что приложение установлено в C:\\Users\\56\\AppData\\Local\\Tesseract-OCR"
        )
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


class ScreenAnalyzer:
    """Класс для захвата экрана, OCR и анализа пикселей."""

    @staticmethod
    def capture_screen() -> Image.Image:
        """Снимок всего экрана (все мониторы складываются в одно изображение)."""
        with mss.mss() as sct:
            monitor = sct.monitors[0]  # 0 = объединённая область всех мониторов
            shot = sct.grab(monitor)
            return Image.frombytes("RGB", shot.size, shot.rgb)

    @staticmethod
    def capture_region(x: int, y: int, width: int, height: int) -> Image.Image:
        """Снимок прямоугольной области экрана по координатам x, y, width, height."""
        with mss.mss() as sct:
            region = {
                "left": max(0, x),
                "top": max(0, y),
                "width": max(1, width),
                "height": max(1, height),
            }
            shot = sct.grab(region)
            img = Image.frombytes("RGB", shot.size, shot.rgb)
            if DEBUG_SAVE_REGION:
                img.save(f"captregion_{int(time.time() * 1000)}.png")    
            return img

    @staticmethod
    def get_text_in_region(x: int, y: int, width: int, height: int, lang: str = LANG) -> str:
        """Получить текст из области экрана по координатам."""
        #для отладки можно сохранить снимок области в файл:
        
        _ensure_tesseract()
        image = ScreenAnalyzer.capture_region(x, y, width, height)
        text = pytesseract.image_to_string(image, lang=lang)
        if DEBUG_SAVE_REGION:
            image.save(f"gettext____{int(time.time() * 1000)}.png")
        return text.strip()

    @staticmethod
    def get_pixels_colors_in_region(
        x: int,
        y: int,
        width: int,
        height: int,
        as_2d: bool = False,
    ) -> List[Tuple[int, int, int]] | List[List[Tuple[int, int, int]]]:
        """Получить массив цветов RGB точек в области экрана.

        По умолчанию возвращается плоский список из width * height элементов.
        Если as_2d=True, возвращается двумерный массив по строкам.
        """
        image = ScreenAnalyzer.capture_region(x, y, width, height)
        if DEBUG_SAVE_REGION:
            image.save(f"getpixls____{int(time.time() * 1000)}.png")
        pixels: List[Tuple[int, int, int]] = []

        for row in range(height):
            row_pixels: List[Tuple[int, int, int]] = []
            for col in range(width):
                pixel = image.getpixel((col, row))
                if as_2d:
                    row_pixels.append(pixel)
                else:
                    pixels.append(pixel)
            if as_2d:
                pixels.append(row_pixels)

        return pixels

    @staticmethod
    def color_matches(pixel: Tuple[int, int, int], target_color: Tuple[int, int, int], tolerance: int = 0) -> bool:
        """Проверить, совпадает ли цвет пикселя с target_color с допустимым отклонением."""
        return all(abs(pixel[i] - target_color[i]) <= tolerance for i in range(3))

    @staticmethod
    def count_color_pixels_in_region(
        x: int,
        y: int,
        width: int,
        height: int,
        target_color: Tuple[int, int, int],
        tolerance: int = 0,
    ) -> int:
        """Сколько пикселей области совпадают с target_color (с допуском)."""
        image = ScreenAnalyzer.capture_region(x, y, width, height)
        if DEBUG_SAVE_REGION:
            image.save(f"region_{int(time.time() * 1000)}.png")  # для отладки
        return sum(
            1
            for pixel in image.getdata()
            if ScreenAnalyzer.color_matches(pixel, target_color, tolerance)
        )

    @staticmethod
    def has_color_in_region(
        x: int,
        y: int,
        width: int,
        height: int,
        target_color: Tuple[int, int, int],
        tolerance: int = 0,
        min_pixels: int = 1,
    ) -> bool:
        """Есть ли в области хотя бы min_pixels пикселей нужного цвета."""
        count = ScreenAnalyzer.count_color_pixels_in_region(
            x, y, width, height, target_color, tolerance
        )
        return count >= min_pixels

    @staticmethod
    def get_first_non_color_y_in_region(
        x: int,
        y: int,
        width: int,
        height: int,
        target_color: Tuple[int, int, int],
        tolerance: int = 0,
    ) -> int | None:
        """Вернуть Y координату первого пикселя в прямоугольнике, который отличается от target_color.

        Поиск идёт сверху вниз и слева направо. Если все пиксели совпадают, возвращается None.
        """
        image = ScreenAnalyzer.capture_region(x, y, width, height)

        for row in range(height):
            for col in range(width):
                pixel = image.getpixel((col, row))
                if not ScreenAnalyzer.color_matches(pixel, target_color, tolerance):
                    return y + row

        return None

    @staticmethod
    def click_in_place(x: int, y: int, button: str = "left", clicks: int = 1, interval: float = 0.0) -> None:
        """Кликнуть левой/правой кнопкой мыши в указанное место."""
        pyautogui.click(x=x, y=y, button=button, clicks=clicks, interval=interval)
        return



    @staticmethod
    def move_mouse_to(x: int, y: int, duration: float = 0.0) -> None:
        """Переместить мышь в указанное место за duration секунд."""
        pyautogui.moveTo(x=x, y=y, duration=duration)

    @staticmethod
    def type_text(text: str, interval: float = 0.0) -> None:
        """Имитировать ввод текста с клавиатуры (только ASCII-символы)."""
        if not text:
            return
        pyautogui.typewrite(text, interval=interval)

    @staticmethod
    def type_text_clipboard(text: str) -> None:
        """Ввести текст через буфер обмена (Ctrl+V) — поддерживает кириллицу."""
        if not text:
            return
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")

    @staticmethod
    def get_clipboard_text() -> str:
        """Прочитать текстовый содержимое буфера обмена ("" если буфер пуст/не текст)."""
        return pyperclip.paste() or ""

    @staticmethod
    def set_clipboard_text(text: str) -> None:
        """Положить текст в буфер обмена (без ввода с клавиатуры)."""
        pyperclip.copy(text)

    @staticmethod
    def press_key(key: str) -> None:
        """Нажать клавишу клавиатуры (например, 'enter')."""
        pyautogui.press(key)

    @staticmethod
    def scroll_at(x: int, y: int, direction: int, amount: int = 5) -> None:
        """Повернуть колёсико мыши над точкой (x, y).

        direction: 1 — прокрутить вверх, -1 — вниз. amount — щелчки колёсика.
        """
        if direction not in (SCROLL_UP, SCROLL_DOWN):
            raise ValueError(
                f"direction должен быть {SCROLL_UP} (вверх) или {SCROLL_DOWN} (вниз), получено: {direction}"
            )
        pyautogui.moveTo(x, y)
        pyautogui.scroll(direction * amount)

    @staticmethod
    def find_window(title: str):
        """Найти окно по заголовку. Вернуть объект окна или None."""
        windows = pyautogui.getWindowsWithTitle(title)
        return windows[0] if windows else None

    @staticmethod
    def activate_window(window) -> None:
        """Активировать окно: развернуть, если свёрнуто, и вывести на передний план."""
        if window.isMinimized:
            window.restore()
        try:
            window.activate()
        except Exception:  # noqa: BLE001 - Windows может запретить поднятие окна
            # Запасной путь: кликнуть по заголовку окна
            pyautogui.click(window.left + window.width // 2, window.top + 10)

    @staticmethod
    def ocr_image(image: Image.Image) -> str:
        _ensure_tesseract()
        text = pytesseract.image_to_string(image, lang=LANG)
        return text.strip()

    def main(self) -> None:
        print(f"Запуск. Интервал {INTERVAL} с, вывод в {OUTPUT_FILE}")
        while True:
            started = time.monotonic()
            try:
                text = self.ocr_image(self.capture_screen())
                stamp = datetime.now().strftime("%H:%M:%S")
                OUTPUT_FILE.write_text(f"[{stamp}] распознано {len(text)} символов", encoding="utf-8")
                print(f"[{stamp}] распознано {len(text)} символов")
            except Exception as exc:  # noqa: BLE001 - не роняем цикл из-за сбоя кадра
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ошибка: {exc}")

            elapsed = time.monotonic() - started
            time.sleep(max(0.0, INTERVAL - elapsed))


if __name__ == "__main__":
    ScreenAnalyzer().main()


