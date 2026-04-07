"""OCR-утилиты: поиск Tesseract, распознавание, сопоставление токенов (§10.10 SCRIPT_RULES)."""

import os
import platform
import re
import shutil
import subprocess
from typing import List, Optional, Tuple


def _is_windows():
    return platform.system() == "Windows"


def _is_linux():
    return platform.system() == "Linux"


def _is_macos():
    return platform.system() == "Darwin"


def find_tesseract() -> Optional[str]:
    path = shutil.which("tesseract")
    if path:
        return path
    if _is_windows():
        candidates = [
            os.path.join(os.environ.get("ProgramFiles", ""),
                         "Tesseract-OCR", "tesseract.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""),
                         "Tesseract-OCR", "tesseract.exe"),
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]
    elif _is_linux():
        candidates = ["/usr/bin/tesseract", "/usr/local/bin/tesseract"]
    elif _is_macos():
        candidates = ["/usr/local/bin/tesseract", "/opt/homebrew/bin/tesseract"]
    else:
        candidates = []
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None


def ocr_image(image_path: str) -> str:
    """Запустить OCR на изображении (два режима PSM для устойчиво��ти)."""
    tesseract = find_tesseract()
    if not tesseract:
        return ""
    parts = []
    for psm in (6, 11):
        try:
            r = subprocess.run(
                [tesseract, image_path, "stdout",
                 "-l", "rus+eng", "--oem", "1", "--psm", str(psm)],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30,
            )
            if r.stdout.strip():
                parts.append(r.stdout.strip())
        except Exception:
            pass
    return "\n".join(parts).strip() if parts else ""


def _normalize(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"[^A-ZА-Я0-9]", "", s.upper().replace("Ё", "Е"))


def has_tokens(text: str, tokens: List[str], need: int = 1) -> Tuple[bool, List[str]]:
    """Проверить наличие токенов в тексте (мягкое OCR-совпадение)."""
    norm = _normalize(text)
    found: List[str] = []
    for token in tokens:
        tn = _normalize(token)
        if not tn:
            continue
        if tn in norm:
            found.append(token)
            continue
        if len(tn) >= 6:
            prefix = tn[:5]
            suffix = tn[-4:]
            if prefix in norm and suffix in norm:
                found.append(token)
    return len(found) >= need, found


def find_token_bbox(image_path: str, token: str) -> Optional[dict]:
    """Найти bbox токена по реальным координатам из Tesseract TSV.

    Возвращает dict {'center_x','center_y','left','top','width','height'}
    в системе координат изображения, или None если токен не найден.
    Использует `-c preserve_interword_spaces=1` и TSV-выход для надёжности.
    """
    tesseract = find_tesseract()
    if not tesseract or not token:
        return None
    tn = _normalize(token)
    if not tn:
        return None

    best = None  # (score, dict) — берём кандидата с самым длинным совпадением
    for psm in (6, 11):
        try:
            r = subprocess.run(
                [tesseract, image_path, "stdout",
                 "-l", "rus+eng", "--oem", "1", "--psm", str(psm), "tsv"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30,
            )
        except Exception:
            continue
        if not r.stdout:
            continue

        # Соберём слова по строкам (page, block, par, line) и объединим их
        # bbox'ы, чтобы матчить многословные токены типа «Локальные файлы».
        lines = {}  # key -> list of (left, top, right, bottom, text)
        for raw in r.stdout.splitlines()[1:]:
            parts = raw.split("\t")
            if len(parts) < 12:
                continue
            try:
                level = int(parts[0])
                page, block, par, line = parts[1], parts[2], parts[3], parts[4]
                left = int(parts[6]); top = int(parts[7])
                w = int(parts[8]); h = int(parts[9])
                word = parts[11]
            except ValueError:
                continue
            if level != 5 or not word.strip():
                continue
            key = (page, block, par, line)
            lines.setdefault(key, []).append(
                (left, top, left + w, top + h, word)
            )

        for words in lines.values():
            # Скользящее окно по словам строки: склеиваем нормализованный текст
            # и ищем вхождение tn. Так ловим и одно слово, и «Локальные файлы».
            for i in range(len(words)):
                acc_norm = ""
                min_left = words[i][0]; max_right = words[i][2]
                min_top = words[i][1]; max_bot = words[i][3]
                for j in range(i, len(words)):
                    w = words[j]
                    acc_norm += _normalize(w[4])
                    if w[0] < min_left: min_left = w[0]
                    if w[2] > max_right: max_right = w[2]
                    if w[1] < min_top: min_top = w[1]
                    if w[3] > max_bot: max_bot = w[3]
                    if tn in acc_norm:
                        bbox_w = max_right - min_left
                        bbox_h = max_bot - min_top
                        cand = {
                            'left': min_left, 'top': min_top,
                            'width': bbox_w, 'height': bbox_h,
                            'center_x': min_left + bbox_w // 2,
                            'center_y': min_top + bbox_h // 2,
                        }
                        score = len(acc_norm)
                        if best is None or score < best[0]:
                            best = (score, cand)
                        break
    return best[1] if best else None


def find_token_position(text: str, token: str, image_width: int, image_height: int) -> Optional[dict]:
    """Найти approximate позицию токена в изображении на основе OCR текста.
    
    Возвращает dict с 'center_x', 'center_y' или None, если токен не найден.
    """
    if not text or not token:
        return None
    
    tn = _normalize(token)
    lines = text.strip().split('\n')
    
    for line_idx, line in enumerate(lines):
        norm_line = _normalize(line)
        if tn in norm_line:
            # Токен найден в строке
            # Оценим позицию строки в изображении
            # (приближённо: равномерное распределение строк)
            total_lines = len(lines)
            if total_lines == 0:
                return None
            
            # Средняя высота строки
            line_height = image_height / max(total_lines, 1)
            
            # Центр строки по Y
            center_y = int((line_idx + 0.5) * line_height)
            
            # По X: найдём позицию токена в строке
            if norm_line and tn:
                token_start = norm_line.find(tn)
                if token_start >= 0:
                    # Доля строки, где находится токен
                    token_ratio_start = token_start / len(norm_line)
                    token_ratio_width = len(tn) / len(norm_line)
                    
                    # Позиция центра токена по X
                    center_x = int((token_ratio_start + token_ratio_width / 2) * image_width)
                    
                    return {
                        'center_x': center_x,
                        'center_y': center_y,
                        'line_index': line_idx,
                    }
    
    return None
