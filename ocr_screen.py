"""Скриншот экрана -> OCR -> текстовый файл.

Каждые 5 секунд снимает весь экран, распознавает текст (русский + английский)
и записывает его в output.txt (перезаписывая файл целиком).
"""

import time
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import mss
import pyautogui
import pytesseract
from PIL import Image

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
OUTPUT_FILE = Path(__file__).with_name("output.txt")
INTERVAL = 5  # секунд
LANG = "rus+eng"

pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


def capture_screen() -> Image.Image:
    """Снимок всего экрана (все мониторы складываются в одно изображение)."""
    with mss.mss() as sct:
        monitor = sct.monitors[0]  # 0 = объединённая область всех мониторов
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.rgb)


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
        return Image.frombytes("RGB", shot.size, shot.rgb)


def get_text_in_region(x: int, y: int, width: int, height: int, lang: str = LANG) -> str:
    """Получить текст из области экрана по координатам."""
    image = capture_region(x, y, width, height)
    text = pytesseract.image_to_string(image, lang=lang)
    return text.strip()


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
    image = capture_region(x, y, width, height)
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


def click_in_place(x: int, y: int, button: str = "left", clicks: int = 1, interval: float = 0.0) -> None:
    """Кликнуть левой/правой кнопкой мыши в указанное место."""
    pyautogui.click(x=x, y=y, button=button, clicks=clicks, interval=interval)


def type_text(text: str, interval: float = 0.0) -> None:
    """Имитировать ввод текста с клавиатуры."""
    if not text:
        return
    pyautogui.typewrite(text, interval=interval)


def ocr_image(image: Image.Image) -> str:
    text = pytesseract.image_to_string(image, lang=LANG)
    return text.strip()


def main() -> None:
    print(f"Запуск. Интервал {INTERVAL} с, вывод в {OUTPUT_FILE}")
    while True:
        started = time.monotonic()
        try:
            text = ocr_image(capture_screen())
            OUTPUT_FILE.write_text(text, encoding="utf-8")
            stamp = datetime.now().strftime("%H:%M:%S")
            print(f"[{stamp}] распознано {len(text)} символов")
        except Exception as exc:  # noqa: BLE001 - не роняем цикл из-за сбоя кадра
            print(f"[{datetime.now().strftime('%H:%M:%S')}] ошибка: {exc}")

        elapsed = time.monotonic() - started
        time.sleep(max(0.0, INTERVAL - elapsed))


if __name__ == "__main__":
    main()
