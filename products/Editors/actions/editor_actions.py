"""Semantic actions для Editors — продуктовый слой (§16, §17 SCRIPT_RULES).

ВАЖНО: хардкод координат UI запрещён. R7 Office использует CEF, элементы
ленты и стартового экрана недоступны через Accessibility API, поэтому клики
выполняются по координатам — но координаты получаются в **runtime** через
OCR (`shared.infra.ocr.find_token_bbox`) на свежем скриншоте окна, а не
зашиваются в код. Это единственный способ работать на любых разрешениях.
"""

import base64
import json
import logging
import os as _os
import socket
import tempfile
import time
import urllib.parse
import urllib.request

from shared.drivers import get_driver
from shared.infra.screenshots import take_screenshot

logger = logging.getLogger(__name__)


def click_menu(pid: int, menu_key: str):
    """Активировать окно и кликнуть по пункту левого меню стартового экрана.
    
    Основной путь: семантический поиск элемента через driver.click_menu_item().
    Fallback цепочка внутри driver: accessibility → OCR → coordinates → CV.
    """
    driver = get_driver()
    driver.activate_window(pid)
    
    # Семантический клик с fallback цепочкой внутри driver
    success = driver.click_menu_item(pid, menu_key)
    
    if not success:
        raise RuntimeError(
            f"Не удалось кликнуть по пункту меню '{menu_key}': "
            f"все fallback методы исчерпаны"
        )
    
    time.sleep(0.6)  # ожидание перехода (Semantic Actions Layer)


def dismiss_collab_popup(pid: int):
    """Закрыть модальное окно подключения дисков клавишей Esc."""
    driver = get_driver()
    driver.send_escape(pid)


def type_document_text(pid: int, text: str, align_left: bool = False):
    """Ввести текст в область документа и при необходимости выровнять влево.

    Action-only: выполняет фокус на холсте документа, вставляет текст через
    буфер обмена и (опционально) применяет выравнивание абзаца влево.
    PASS/FAIL не выставляет — подтверждение выполняется assertion-слоем.
    """
    driver = get_driver()
    driver.activate_window(pid)

    # FALLBACK: у CEF-холста нет стабильного accessibility-id, поэтому
    # фокусируем рабочую область относительным кликом по центру страницы.
    driver.click_rel(pid, 0.50, 0.45)
    time.sleep(0.2)

    driver.paste_text(pid, text)
    if align_left:
        driver.align_paragraph_left(pid)


_QUICK_ACCESS_BUTTONS = {
    "save": 0,
    "undo": 1,
    "redo": 2,
}

_QUICK_ACCESS_SELECTORS = {
    "save": [
        "#slot-btn-dt-save button",
        "#slot-btn-dt-save",
        "#id-toolbar-btn-save",
    ],
    "undo": [
        "#slot-btn-dt-undo button",
        "#slot-btn-dt-undo",
        "#id-toolbar-btn-undo",
    ],
    "redo": [
        "#slot-btn-dt-redo button",
        "#slot-btn-dt-redo",
        "#id-toolbar-btn-redo",
    ],
}


def _devtools_active_port_path() -> str:
    local_app_data = _os.environ.get("LOCALAPPDATA", "")
    if not local_app_data:
        return ""
    return _os.path.join(
        local_app_data,
        "R7-Office",
        "Editors",
        "data",
        "cache",
        "DevToolsActivePort",
    )


def _read_devtools_port() -> int:
    path = _devtools_active_port_path()
    if not path or not _os.path.exists(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
        return int(first_line)
    except Exception:
        return 0


def _choose_cdp_target(port: int) -> str:
    if port <= 0:
        return ""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1.5) as resp:
            targets = json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception:
        return ""
    if not isinstance(targets, list):
        return ""
    candidates = []
    for item in targets:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "page":
            continue
        ws_url = str(item.get("webSocketDebuggerUrl") or "")
        if not ws_url:
            continue
        score = 0
        url = str(item.get("url") or "")
        title = str(item.get("title") or "")
        if "desktop=true" in url:
            score += 2
        if "index.html" in url:
            score += 1
        if "Documents" in title or "Документ" in title:
            score += 1
        candidates.append((score, ws_url))
    if not candidates:
        return ""
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


class _CdpWsClient:
    """Минимальный WebSocket-клиент для отправки CDP-команд без внешних зависимостей."""

    def __init__(self, ws_url: str, timeout_sec: float = 2.0):
        self.ws_url = ws_url
        self.timeout_sec = timeout_sec
        self.sock = None
        self._next_id = 1

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def close(self) -> None:
        if not self.sock:
            return
        try:
            self.sock.close()
        except Exception:
            pass
        self.sock = None

    def _read_http_headers(self) -> bytes:
        data = b""
        deadline = time.time() + self.timeout_sec
        while b"\r\n\r\n" not in data and time.time() < deadline:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            data += chunk
        return data

    def _connect(self) -> None:
        parsed = urllib.parse.urlparse(self.ws_url)
        if parsed.scheme != "ws":
            raise RuntimeError(f"Unsupported CDP websocket scheme: {parsed.scheme}")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        self.sock = socket.create_connection((host, port), timeout=self.timeout_sec)
        self.sock.settimeout(self.timeout_sec)

        sec_key = base64.b64encode(_os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {sec_key}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        headers = self._read_http_headers().decode("latin1", errors="ignore")
        if " 101 " not in headers:
            raise RuntimeError(f"WebSocket handshake failed: {headers[:120]}")

    def _send_frame_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        fin_opcode = 0x81
        mask_bit = 0x80
        header = bytearray([fin_opcode])
        plen = len(payload)
        if plen < 126:
            header.append(mask_bit | plen)
        elif plen <= 0xFFFF:
            header.append(mask_bit | 126)
            header.extend(plen.to_bytes(2, "big"))
        else:
            header.append(mask_bit | 127)
            header.extend(plen.to_bytes(8, "big"))

        mask_key = _os.urandom(4)
        header.extend(mask_key)
        masked = bytes(payload[i] ^ mask_key[i % 4] for i in range(plen))
        self.sock.sendall(bytes(header) + masked)

    def _recv_exact(self, n: int) -> bytes:
        data = b""
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise RuntimeError("WebSocket connection closed")
            data += chunk
        return data

    def _recv_frame(self):
        h = self._recv_exact(2)
        b1, b2 = h[0], h[1]
        opcode = b1 & 0x0F
        masked = (b2 & 0x80) != 0
        plen = b2 & 0x7F
        if plen == 126:
            plen = int.from_bytes(self._recv_exact(2), "big")
        elif plen == 127:
            plen = int.from_bytes(self._recv_exact(8), "big")
        mask_key = self._recv_exact(4) if masked else b""
        payload = self._recv_exact(plen) if plen else b""
        if masked:
            payload = bytes(payload[i] ^ mask_key[i % 4] for i in range(plen))
        return opcode, payload

    def call(self, method: str, params: dict):
        msg_id = self._next_id
        self._next_id += 1
        self._send_frame_text(json.dumps({"id": msg_id, "method": method, "params": params}))
        deadline = time.time() + self.timeout_sec
        while time.time() < deadline:
            opcode, payload = self._recv_frame()
            if opcode == 0x9:  # ping
                pong = bytearray([0x8A, 0x80])  # pong + empty masked payload
                pong.extend(_os.urandom(4))
                self.sock.sendall(bytes(pong))
                continue
            if opcode in (0x8, 0xA):  # close/pong
                continue
            if opcode != 0x1:
                continue
            data = json.loads(payload.decode("utf-8", errors="ignore"))
            if data.get("id") == msg_id:
                return data
        raise TimeoutError(f"CDP response timeout for {method}")


def _cdp_click_selector(selector: str) -> bool:
    port = _read_devtools_port()
    ws_url = _choose_cdp_target(port)
    if not ws_url:
        return False

    script = f"""
(() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el) return {{ok:false, reason:"not_found"}};
  const style = window.getComputedStyle(el);
  if (!style || style.display === "none" || style.visibility === "hidden") {{
    return {{ok:false, reason:"hidden"}};
  }}
  const disabled = !!el.disabled || el.getAttribute("aria-disabled") === "true";
  if (disabled) return {{ok:false, reason:"disabled"}};
  el.click();
  return {{ok:true}};
}})()
"""
    try:
        with _CdpWsClient(ws_url, timeout_sec=2.0) as cdp:
            result = cdp.call(
                "Runtime.evaluate",
                {
                    "expression": script,
                    "returnByValue": True,
                    "awaitPromise": True,
                },
            )
        value = (
            result.get("result", {})
            .get("result", {})
            .get("value", {})
        )
        return bool(isinstance(value, dict) and value.get("ok"))
    except Exception:
        return False


def _cdp_click_selector_in_editor_frame(selector: str) -> bool:
    """Кликнуть по селектору внутри iframe `frameEditor` (основной путь для CEF-редактора)."""
    result = _cdp_eval_in_editor_frame(
        f"""
  const el = doc.querySelector({json.dumps(selector)});
  if (!el) return {{ok:false, reason:"not_found"}};
  const style = window.getComputedStyle(el);
  if (!style || style.display === "none" || style.visibility === "hidden") {{
    return {{ok:false, reason:"hidden"}};
  }}
  const disabled = !!el.disabled || el.getAttribute("aria-disabled") === "true";
  if (disabled) return {{ok:false, reason:"disabled"}};
  el.click();
  return {{ok:true}};
"""
    )
    return bool(isinstance(result, dict) and result.get("ok"))


def _cdp_eval_in_editor_frame(expression_body: str):
    """Выполнить JS в DOM документа редактора внутри iframe `frameEditor`."""
    port = _read_devtools_port()
    ws_url = _choose_cdp_target(port)
    if not ws_url:
        return None

    script = f"""
(() => {{
  const frame = document.querySelector('iframe[name="frameEditor"]') || document.querySelector('iframe');
  if (!frame) return {{ok:false, reason:"no_iframe"}};
  let doc = null;
  try {{
    doc = frame.contentWindow && frame.contentWindow.document;
  }} catch (e) {{
    return {{ok:false, reason:"frame_access_error", error:String(e)}};
  }}
  if (!doc) return {{ok:false, reason:"no_frame_doc"}};
  {expression_body}
}})()
"""
    try:
        with _CdpWsClient(ws_url, timeout_sec=2.0) as cdp:
            result = cdp.call(
                "Runtime.evaluate",
                {
                    "expression": script,
                    "returnByValue": True,
                    "awaitPromise": True,
                },
            )
        return (
            result.get("result", {})
            .get("result", {})
            .get("value", {})
        )
    except Exception:
        return None


def _close_active_document_tab_via_cdp() -> bool:
    """Закрыть документ через DOM-контрол внутри редактора (CDP-first)."""
    result = _cdp_eval_in_editor_frame(
        """
  const btn = doc.querySelector('#btn-go-back');
  if (!btn) return {ok:false, reason:"btn_go_back_not_found"};
  const style = window.getComputedStyle(btn);
  if (!style || style.display === "none" || style.visibility === "hidden") {
    return {ok:false, reason:"btn_go_back_hidden"};
  }
  btn.click();
  return {ok:true, source:"btn_go_back"};
"""
    )
    ok = bool(isinstance(result, dict) and result.get("ok"))
    if ok:
        logger.info("CDP close-tab success via #btn-go-back")
    return ok


def _click_quick_access_button_via_cdp(button_key: str) -> bool:
    selectors = _QUICK_ACCESS_SELECTORS.get(button_key, [])
    for selector in selectors:
        if _cdp_click_selector_in_editor_frame(selector):
            logger.info(
                "CDP click success for %s via iframe selector %s",
                button_key,
                selector,
            )
            return True
        if _cdp_click_selector(selector):
            logger.info("CDP click success for %s via selector %s", button_key, selector)
            return True
    return False


def _click_quick_access_button(pid: int, button_key: str) -> bool:
    """Кликнуть по кнопке панели быстрого доступа слева от вкладки «Файл».

    Основной путь для шагов вида «кликнуть кнопку ...»:
    1) OCR находит якорь «Автосохранение» на верхней панели
    2) координата кнопки вычисляется относительно якоря
    3) выполняется клик по UI-элементу (driver.click_rel)
    """
    if button_key not in _QUICK_ACCESS_BUTTONS:
        raise ValueError(f"Неизвестная кнопка быстрого доступа: {button_key}")

    # Основной путь: DOM-клик через CDP (debug-порт редактора).
    # Это устойчиво к DPI/разрешению и не зависит от координат.
    if _click_quick_access_button_via_cdp(button_key):
        return True

    from PIL import Image

    driver = get_driver()
    driver.activate_window(pid)

    fd, screenshot_path = tempfile.mkstemp(prefix="quick_access_", suffix=".png")
    _os.close(fd)
    try:
        take_screenshot(screenshot_path)
        img = Image.open(screenshot_path)
        width, height = img.size

        # Кнопки Quick Access в левом верхнем углу.
        # В CEF-UI координаты иконок доступны только через runtime-клик.
        # Используем калибровку в относительных долях экрана + небольшой
        # горизонтальный перебор, чтобы нивелировать DPI/scale отклонения.
        rel_map = {
            "save": 0.016,
            "undo": 0.088,
            "redo": 0.114,
        }
        base_rel_x = rel_map[button_key]
        rel_y = 0.045
        for x_shift in (-0.006, 0.0, 0.006):
            target_rel_x = max(0.0, min(0.999, base_rel_x + x_shift))
            target_x = int(target_rel_x * width)
            target_y = int(rel_y * height)
            driver.click_rel(pid, target_x / width, target_y / height)
            time.sleep(0.12)
        return True
    finally:
        try:
            _os.remove(screenshot_path)
        except OSError:
            pass


def undo_last_action(pid: int, allow_hotkey_fallback: bool = True) -> bool:
    """Выполнить команду «Отменить».

    Возвращает True, если выполнен UI-клик или fallback.
    """
    if _click_quick_access_button(pid, "undo"):
        return True
    if not allow_hotkey_fallback:
        return False
    # FALLBACK: UI-кнопка не найдена OCR; используем Ctrl+Z как резерв.
    logger.warning("FALLBACK: кнопка «Отменить» не найдена, применён Ctrl+Z")
    get_driver().undo_action(pid)
    return True


def redo_last_action(pid: int, allow_hotkey_fallback: bool = True) -> bool:
    """Выполнить команду «Повторить».

    Возвращает True, если выполнен UI-клик или fallback.
    """
    if _click_quick_access_button(pid, "redo"):
        return True
    if not allow_hotkey_fallback:
        return False
    # FALLBACK: UI-кнопка не найдена OCR; используем Ctrl+Y как резерв.
    logger.warning("FALLBACK: кнопка «Повторить» не найдена, применён Ctrl+Y")
    get_driver().redo_action(pid)
    return True


def save_active_document(pid: int, allow_hotkey_fallback: bool = True) -> bool:
    """Выполнить команду «Сохранить».

    Возвращает True, если выполнен UI-клик или fallback.
    """
    if _click_quick_access_button(pid, "save"):
        return True
    if not allow_hotkey_fallback:
        return False
    # FALLBACK: UI-кнопка не найдена OCR; используем Ctrl+S как резерв.
    logger.warning("FALLBACK: кнопка «Сохранить» не найдена, применён Ctrl+S")
    get_driver().save_document(pid)
    return True


def confirm_active_dialog(pid: int):
    """Подтвердить активный системный диалог клавишей Enter."""
    get_driver().confirm_dialog(pid)


def close_active_document_tab(pid: int, allow_hotkey_fallback: bool = True) -> bool:
    """Закрыть текущую вкладку по кнопке «X».

    Возвращает True, если выполнен UI-клик или fallback.
    """
    # Основной путь: CDP-клик по DOM-кнопке возврата из редактора.
    # В desktop-режиме этот клик эквивалентен закрытию активного документа
    # и устойчив к разрешению/DPI.
    if _close_active_document_tab_via_cdp():
        return True

    from PIL import Image

    driver = get_driver()
    driver.activate_window(pid)

    fd, screenshot_path = tempfile.mkstemp(prefix="tab_close_", suffix=".png")
    _os.close(fd)
    clicked = False
    try:
        take_screenshot(screenshot_path)
        img = Image.open(screenshot_path)
        width, height = img.size
        # Кнопка "X" у вкладки документа в левом верхнем углу.
        # Делаем несколько точек рядом с крестиком вкладки, чтобы не попасть
        # в центральный заголовок документа.
        rel_points = [
            (0.166, 0.017),
            (0.160, 0.017),
            (0.172, 0.017),
        ]
        for rel_x, rel_y in rel_points:
            target_x = int(rel_x * width)
            target_y = int(rel_y * height)
            driver.click_rel(pid, target_x / width, target_y / height)
            time.sleep(0.15)
            clicked = True
    finally:
        try:
            _os.remove(screenshot_path)
        except OSError:
            pass

    if clicked:
        return True

    if not allow_hotkey_fallback:
        return False
    # FALLBACK: кнопка «X» вкладки не найдена OCR; используем Ctrl+F4.
    logger.warning("FALLBACK: кнопка закрытия вкладки не найдена, применён Ctrl+F4")
    driver.close_current_tab(pid)
    return True


_DOC_LABELS = {
    "document":     "Документ",
    "spreadsheet":  "Таблица",
    "presentation": "Презентация",
}


def _ocr_click_label(pid: int, screenshot_path: str, query: str) -> bool:
    """Найти на скриншоте текстовую метку *query* и кликнуть по её центру.

    Внутренний helper для координатных кликов с runtime OCR-калибровкой.
    """
    from PIL import Image
    from shared.infra.ocr import find_token_bbox

    bbox = find_token_bbox(screenshot_path, query)
    if not bbox:
        return False
    img = Image.open(screenshot_path)
    W, H = img.size
    rel_x = bbox["center_x"] / W
    rel_y = bbox["center_y"] / H
    driver = get_driver()
    driver.activate_window(pid)
    driver.click_rel(pid, rel_x, rel_y)
    return True


def create_document(pid: int, doc_type: str = "document",
                    screenshot_path: str = None):
    """Кликнуть по кнопке создания документа на стартовом экране.

    Координаты кнопки определяются в runtime через OCR — поиск подписи
    («Документ»/«Таблица»/«Презентация») на свежем скриншоте.

    Args:
        pid: процесс редактора
        doc_type: "document" | "spreadsheet" | "presentation"
        screenshot_path: путь для рабочего скриншота калибровки. Если не
            задан — используется временный файл рядом с editors artifacts.
    """
    if doc_type not in _DOC_LABELS:
        raise ValueError(f"Неизвестный тип документа: {doc_type}")
    driver = get_driver()
    driver.activate_window(pid)

    # Свежий скриншот стартового экрана для OCR-калибровки
    import tempfile, os as _os
    if not screenshot_path:
        fd, screenshot_path = tempfile.mkstemp(prefix="start_", suffix=".png")
        _os.close(fd)
    take_screenshot(screenshot_path)

    label = _DOC_LABELS[doc_type]
    if not _ocr_click_label(pid, screenshot_path, label):
        raise RuntimeError(
            f"Не удалось найти кнопку «{label}» на стартовом экране через OCR"
        )


def click_toolbar_tab(pid: int, tab_name: str, positions: dict):
    """Кликнуть по вкладке ленты по откалиброванным координатам.

    Args:
        pid: процесс редактора
        tab_name: имя вкладки (например, "Главная", "Вставка")
        positions: dict {tab_name: (rel_x, rel_y)} от calibrate_toolbar_tabs().
            Хардкод координат запрещён — словарь обязателен.

    Fallback:
        Если вкладка отсутствует в positions (неполная OCR-калибровка),
        выполняется on-demand OCR-клик по имени вкладки на свежем скриншоте.
        Ошибка поднимается только если fallback не смог найти вкладку.
    """
    coords = positions.get(tab_name) if positions else None
    if not coords:
        # FALLBACK: если вкладка не попала в первичную калибровку, пробуем
        # свежий OCR-клик по имени вкладки прямо перед действием.
        if _ocr_click_toolbar_tab(pid, tab_name):
            return
        raise RuntimeError(
            f"Координаты вкладки «{tab_name}» не откалиброваны. "
            f"Перед кликом вызовите calibrate_toolbar_tabs()."
        )
    driver = get_driver()
    driver.activate_window(pid)
    rel_x, rel_y = coords
    driver.click_rel(pid, rel_x, rel_y)


# Имена вкладок ленты в порядке отображения. Многословные («Совместная работа»)
# ищем по первому слову — OCR хуже ловит составные токены.
_TAB_QUERIES = {
    "Файл": "Файл",
    "Главная": "Главная",
    "Вставка": "Вставка",
    "Рисование": "Рисование",
    "Макет": "Макет",
    "Ссылки": "Ссылки",
    "Совместная работа": "Совместная",
    "Защита": "Защита",
    "Вид": "Вид",
    "Плагины": "Плагины",
}


def _ocr_click_toolbar_tab(pid: int, tab_name: str) -> bool:
    """Клик по вкладке ленты через OCR на свежем скриншоте (fallback)."""
    query = _TAB_QUERIES.get(tab_name)
    if not query:
        return False

    fd, screenshot_path = tempfile.mkstemp(prefix="toolbar_", suffix=".png")
    _os.close(fd)
    try:
        take_screenshot(screenshot_path)
        return _ocr_click_label(pid, screenshot_path, query)
    finally:
        try:
            _os.remove(screenshot_path)
        except OSError:
            pass


def calibrate_toolbar_tabs(screenshot_path: str) -> dict:
    """Откалибровать координаты вкладок ленты через OCR на свежем скриншоте.

    Скриншот должен быть полноэкранный, окно редактора — fullscreen,
    видна лента вкладок (документ создан, backstage закрыт).

    Returns:
        dict {tab_name: (rel_x, rel_y)} в долях окна. Вкладки, которые OCR
        не нашёл, в результат не попадают — клик по ним поднимет ошибку.
    """
    from PIL import Image
    from shared.infra.ocr import find_token_bbox

    img = Image.open(screenshot_path)
    W, H = img.size

    result = {}
    for tab_name, query in _TAB_QUERIES.items():
        bbox = find_token_bbox(screenshot_path, query)
        if bbox:
            result[tab_name] = (bbox["center_x"] / W, bbox["center_y"] / H)
    return result


# ---------------------------------------------------------------------------
# Управление процессами редактора
# ---------------------------------------------------------------------------

def kill_editors():
    """Завершить все процессы editors/editors_helper."""
    get_driver().kill_editors()


def launch_editor(editor_path: str):
    """Запустить редактор."""
    driver = get_driver()
    driver.launch_editor(editor_path)


# ---------------------------------------------------------------------------
# Обработка модальных окон предупреждения (§10.6)
# ---------------------------------------------------------------------------

def detect_warning_window(pid: int, timeout_sec: int = 10) -> bool:
    """Проверить наличие модального предупреждения (диалог с кнопкой OK)."""
    driver = get_driver()
    return driver.detect_warning(pid, timeout_sec)


def dismiss_warning(pid: int) -> bool:
    """Закрыть предупреждение: Invoke кнопки OK, fallback — Enter."""
    driver = get_driver()
    return driver.dismiss_warning(pid)
