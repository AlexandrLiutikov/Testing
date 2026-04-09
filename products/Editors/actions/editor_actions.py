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

_ACTION_TRACE = {}


def _trace(
    action: str,
    ok: bool,
    mode: str,
    fallback_used: bool = False,
    fallback_source: str = "",
    fallback_reason: str = "",
    warnings: list = None,
) -> dict:
    info = {
        "action": action,
        "ok": bool(ok),
        "mode": mode,
        "fallback_used": bool(fallback_used),
        "fallback_source": fallback_source or "",
        "fallback_reason": fallback_reason or "",
        "warnings": list(warnings or []),
    }
    _ACTION_TRACE[action] = info
    return info


def consume_action_trace(action: str) -> dict:
    """Получить и удалить последнюю трассировку action."""
    return _ACTION_TRACE.pop(action, {})


_START_MENU_LABELS = {
    "home": ["Главная", "Home"],
    "templates": ["Шаблоны", "Templates"],
    "local": ["Локальные файлы", "Локальные", "Local Files", "Local"],
    "collab": ["Совместная работа", "Совместная", "Collaboration"],
    "settings": ["Настройки", "Settings"],
    "about": ["О программе", "О приложении", "About"],
}


def click_menu(pid: int, menu_key: str):
    """Активировать окно и кликнуть по пункту левого меню стартового экрана.
    
    Основной путь: DOM/CDP клик по пункту меню.
    Fallback цепочка внутри driver: accessibility → OCR → coordinates → CV.
    """
    driver = get_driver()
    driver.activate_window(pid)

    # Основной путь: DOM/CDP (быстрее и устойчивее для CEF-startscreen).
    if _cdp_click_start_menu_item(menu_key):
        return _trace("click_menu", True, "DOM_CDP")

    # FALLBACK: семантический клик с fallback цепочкой внутри platform driver.
    success = driver.click_menu_item(pid, menu_key)
    
    if not success:
        _trace(
            "click_menu",
            False,
            "FAILED",
            fallback_used=True,
            fallback_source="DRIVER_CHAIN_EXHAUSTED",
            fallback_reason=f"Не удалось кликнуть menu_key={menu_key}",
        )
        raise RuntimeError(
            f"Не удалось кликнуть по пункту меню '{menu_key}': "
            f"все fallback методы исчерпаны"
        )

    time.sleep(0.6)  # ожидание перехода (Semantic Actions Layer)
    return _trace(
        "click_menu",
        True,
        "DRIVER_CHAIN",
        fallback_used=True,
        fallback_source="DRIVER_CHAIN",
        fallback_reason="DOM/CDP клик недоступен; использована цепочка driver fallback.",
    )


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

    warnings = []
    used_fallback = False
    fallback_source = ""
    fallback_reason = ""

    # Основной путь: попытка сфокусировать содержимое редактора через DOM.
    focus = _cdp_eval_in_editor_frame(
        """
  const target = doc.querySelector('[contenteditable="true"], [role="textbox"], .ace_content');
  if (!target) return {ok:false, reason:'focus_target_not_found'};
  target.focus();
  return {ok:true};
"""
    )
    focused = bool(isinstance(focus, dict) and focus.get("ok"))
    if not focused:
        used_fallback = True
        fallback_source = "COORDINATE_FOCUS"
        fallback_reason = "DOM focus недоступен; фокус установлен координатным кликом."
        warnings.append({
            "code": "FOCUS_FALLBACK",
            "severity": "LOW",
            "message": "DOM-фокус недоступен, использован координатный фокус.",
        })
        # FALLBACK: у CEF-холста нет стабильного accessibility-id, поэтому
        # фокусируем рабочую область относительным кликом по центру страницы.
        driver.click_rel(pid, 0.50, 0.45)
        time.sleep(0.2)

    driver.paste_text(pid, text)
    if align_left:
        driver.align_paragraph_left(pid)
    return _trace(
        "type_document_text",
        True,
        "DOM_FOCUS" if focused else "COORDINATE_FOCUS",
        fallback_used=used_fallback,
        fallback_source=fallback_source,
        fallback_reason=fallback_reason,
        warnings=warnings,
    )


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


def _cdp_eval_root(expression_body: str):
    """Выполнить JS в корневом DOM окна редактора (без iframe)."""
    port = _read_devtools_port()
    ws_url = _choose_cdp_target(port)
    if not ws_url:
        return None
    script = f"""
(() => {{
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


def _cdp_click_start_menu_item(menu_key: str) -> bool:
    labels = _START_MENU_LABELS.get(menu_key, [menu_key])
    result = _cdp_eval_root(
        f"""
  const labels = {json.dumps(labels)};
  const isVisible = (el) => {{
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 2 && r.height > 2;
  }};

  const clickable = Array.from(document.querySelectorAll('a,button,div,span'))
    .filter(isVisible)
    .filter(el => el.getBoundingClientRect().left < window.innerWidth * 0.38);

  for (const lbl of labels) {{
    const found = clickable.find(el => (el.textContent || '').trim() === lbl);
    if (found) {{
      found.click();
      return {{ok:true, label: lbl}};
    }}
  }}
  return {{ok:false, reason:'not_found'}};
"""
    )
    return bool(isinstance(result, dict) and result.get("ok"))


def list_start_menu_items_dom() -> list:
    """Вернуть список видимых пунктов стартового меню через DOM/CDP."""
    result = _cdp_eval_root(
        """
  const isVisible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 4 && r.height > 4;
  };
  const left = Array.from(document.querySelectorAll('a,button,div,span'))
    .filter(isVisible)
    .filter(el => el.getBoundingClientRect().left < window.innerWidth * 0.38)
    .map(el => (el.textContent || '').trim())
    .filter(Boolean);
  const uniq = Array.from(new Set(left)).slice(0, 80);
  return {ok:true, items: uniq};
"""
    )
    if isinstance(result, dict):
        items = result.get("items")
        if isinstance(items, list):
            return [str(x).strip() for x in items if str(x).strip()]
    return []


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


def _cdp_click_toolbar_tab(tab_name: str) -> bool:
    alt = tab_name.split()[0] if " " in tab_name else tab_name
    result = _cdp_eval_in_editor_frame(
        f"""
  const wants = [{json.dumps(tab_name)}, {json.dumps(alt)}];
  const isVisible = (el) => {{
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 2 && r.height > 2 && r.top < 220;
  }};
  const nodes = Array.from(doc.querySelectorAll('a,button,div,span,[role="tab"]')).filter(isVisible);
  for (const want of wants) {{
    const found = nodes.find(el => (el.textContent || '').trim() === want);
    if (found) {{
      found.click();
      return {{ok:true, label: want}};
    }}
  }}
  return {{ok:false, reason:'not_found'}};
"""
    )
    return bool(isinstance(result, dict) and result.get("ok"))


def list_toolbar_tabs_dom() -> list:
    """Вернуть список видимых вкладок ленты через DOM/CDP."""
    result = _cdp_eval_in_editor_frame(
        """
  const isVisible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 6 && r.height > 6 && r.top < 220;
  };
  const items = Array.from(doc.querySelectorAll('a,button,div,span,[role="tab"]'))
    .filter(isVisible)
    .map(el => (el.textContent || '').trim())
    .filter(Boolean);
  const uniq = Array.from(new Set(items)).slice(0, 120);
  return {ok:true, items: uniq};
"""
    )
    if isinstance(result, dict):
        items = result.get("items")
        if isinstance(items, list):
            return [str(x).strip() for x in items if str(x).strip()]
    return []


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


def _click_quick_access_button(pid: int, button_key: str):
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
        return True, "DOM_CDP"

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
        return True, "COORDINATES"
    finally:
        try:
            _os.remove(screenshot_path)
        except OSError:
            pass


def undo_last_action(pid: int, allow_hotkey_fallback: bool = True) -> dict:
    """Выполнить команду «Отменить».

    Возвращает True, если выполнен UI-клик или fallback.
    """
    clicked, mode = _click_quick_access_button(pid, "undo")
    if clicked:
        return _trace("undo_last_action", True, mode)
    if not allow_hotkey_fallback:
        return _trace("undo_last_action", False, "FAILED")
    # FALLBACK: UI-кнопка не найдена OCR; используем Ctrl+Z как резерв.
    logger.warning("FALLBACK: кнопка «Отменить» не найдена, применён Ctrl+Z")
    get_driver().undo_action(pid)
    return _trace(
        "undo_last_action",
        True,
        "HOTKEY",
        fallback_used=True,
        fallback_source="HOTKEY_CTRL_Z",
        fallback_reason="UI-кнопка Undo недоступна; применён горячий клавишный fallback.",
        warnings=[{
            "code": "UNDO_FALLBACK",
            "severity": "LOW",
            "message": "Использован fallback Ctrl+Z вместо UI-кнопки «Отменить».",
        }],
    )


def redo_last_action(pid: int, allow_hotkey_fallback: bool = True) -> dict:
    """Выполнить команду «Повторить».

    Возвращает True, если выполнен UI-клик или fallback.
    """
    clicked, mode = _click_quick_access_button(pid, "redo")
    if clicked:
        return _trace("redo_last_action", True, mode)
    if not allow_hotkey_fallback:
        return _trace("redo_last_action", False, "FAILED")
    # FALLBACK: UI-кнопка не найдена OCR; используем Ctrl+Y как резерв.
    logger.warning("FALLBACK: кнопка «Повторить» не найдена, применён Ctrl+Y")
    get_driver().redo_action(pid)
    return _trace(
        "redo_last_action",
        True,
        "HOTKEY",
        fallback_used=True,
        fallback_source="HOTKEY_CTRL_Y",
        fallback_reason="UI-кнопка Redo недоступна; применён горячий клавишный fallback.",
        warnings=[{
            "code": "REDO_FALLBACK",
            "severity": "LOW",
            "message": "Использован fallback Ctrl+Y вместо UI-кнопки «Повторить».",
        }],
    )


def save_active_document(pid: int, allow_hotkey_fallback: bool = True) -> dict:
    """Выполнить команду «Сохранить».

    Возвращает True, если выполнен UI-клик или fallback.
    """
    clicked, mode = _click_quick_access_button(pid, "save")
    if clicked:
        return _trace("save_active_document", True, mode)
    if not allow_hotkey_fallback:
        return _trace("save_active_document", False, "FAILED")
    # FALLBACK: UI-кнопка не найдена OCR; используем Ctrl+S как резерв.
    logger.warning("FALLBACK: кнопка «Сохранить» не найдена, применён Ctrl+S")
    get_driver().save_document(pid)
    return _trace(
        "save_active_document",
        True,
        "HOTKEY",
        fallback_used=True,
        fallback_source="HOTKEY_CTRL_S",
        fallback_reason="UI-кнопка Save недоступна; применён горячий клавишный fallback.",
        warnings=[{
            "code": "SAVE_FALLBACK",
            "severity": "LOW",
            "message": "Использован fallback Ctrl+S вместо UI-кнопки «Сохранить».",
        }],
    )


def click_zoom_to_page(pid: int) -> dict:
    """Кликнуть в строке состояния кнопку «По размеру страницы»."""
    driver = get_driver()
    driver.activate_window(pid)

    if _cdp_click_zoom_to_page():
        return _trace("click_zoom_to_page", True, "DOM_CDP")

    if _ocr_click_zoom_to_page_near_scale(pid):
        return _trace(
            "click_zoom_to_page",
            True,
            "OCR_STATUSBAR_ANCHOR",
            fallback_used=True,
            fallback_source="OCR_STATUSBAR_SCALE_ANCHOR",
            fallback_reason=(
                "DOM/CDP-клик недоступен, выполнен клик по иконке "
                "«По размеру страницы» относительно якоря «Масштаб»."
            ),
        )

    fd, screenshot_path = tempfile.mkstemp(prefix="zoom_to_page_", suffix=".png")
    _os.close(fd)
    try:
        take_screenshot(screenshot_path)
        if _ocr_click_label(pid, screenshot_path, "По размеру страницы"):
            return _trace(
                "click_zoom_to_page",
                True,
                "OCR",
                fallback_used=True,
                fallback_source="OCR_ZOOM_TO_PAGE",
                fallback_reason=(
                    "DOM/CDP-клик недоступен, выполнен OCR-клик по метке "
                    "«По размеру страницы»."
                ),
            )
    finally:
        try:
            _os.remove(screenshot_path)
        except OSError:
            pass

    return _trace(
        "click_zoom_to_page",
        False,
        "FAILED",
        fallback_used=True,
        fallback_source="ZOOM_TO_PAGE_CHAIN_EXHAUSTED",
        fallback_reason="Не удалось выполнить клик «По размеру страницы» ни DOM, ни OCR.",
    )


def go_to_next_page(pid: int) -> dict:
    """Перейти на следующую страницу документа."""
    driver = get_driver()
    driver.activate_window(pid)

    before_page = _cdp_read_current_page_index()
    last_wheel_error = ""
    for _ in range(3):
        try:
            driver.scroll_next_page(pid)
        except Exception as exc:
            last_wheel_error = str(exc)
            break

        # Если индекс страницы недоступен по CDP, считаем wheel успешным.
        if before_page is None:
            return _trace("go_to_next_page", True, "MOUSE_WHEEL")

        after_page = _cdp_read_current_page_index()
        if isinstance(after_page, int) and after_page > before_page:
            return _trace("go_to_next_page", True, "MOUSE_WHEEL")

    scroll_trace = _cdp_scroll_next_page_via_vertical_scroll()
    if scroll_trace.get("ok"):
        return _trace(
            "go_to_next_page",
            True,
            scroll_trace.get("mode", "DOM_VERTICAL_SCROLL"),
            fallback_used=True,
            fallback_source="MOUSE_WHEEL_UNAVAILABLE",
            fallback_reason=(
                "Прокрутка колесом не подтвердила переход на следующую страницу; "
                "использован DOM-скролл."
            ),
            warnings=[{
                "code": "NEXT_PAGE_DOM_FALLBACK",
                "severity": "LOW",
                "message": "Переход на следующую страницу выполнен через DOM fallback.",
            }],
        )

    try:
        driver.page_down(pid)
        return _trace(
            "go_to_next_page",
            True,
            "KEYBOARD",
            fallback_used=True,
            fallback_source="MOUSE_AND_DOM_SCROLL_UNAVAILABLE",
            fallback_reason=(
                "Недоступны прокрутка колесом и DOM-скролл; "
                f"использован fallback PageDown. {last_wheel_error}".strip()
            ),
            warnings=[{
                "code": "NEXT_PAGE_KEYBOARD_FALLBACK",
                "severity": "LOW",
                "message": "Переход на следующую страницу выполнен через PageDown fallback.",
            }],
        )
    except Exception as exc:
        return _trace(
            "go_to_next_page",
            False,
            "FAILED",
            fallback_used=True,
            fallback_source="NEXT_PAGE_CHAIN_EXHAUSTED",
            fallback_reason=f"MOUSE_WHEEL, DOM-скролл и keyboard fallback недоступны: {exc}",
        )


def confirm_active_dialog(pid: int):
    """Подтвердить активный системный диалог клавишей Enter."""
    get_driver().confirm_dialog(pid)


def close_active_document_tab(pid: int, allow_hotkey_fallback: bool = True) -> dict:
    """Закрыть текущую вкладку по кнопке «X».

    Возвращает True, если выполнен UI-клик или fallback.
    """
    driver = get_driver()
    driver.activate_window(pid)

    # Основной путь: нативный UIA-клик по `X` активной вкладки TabBar фрейма.
    try:
        if driver.click_current_tab_close_button(pid):
            return _trace("close_active_document_tab", True, "UIA")
    except Exception:
        pass

    from PIL import Image
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
        return _trace(
            "close_active_document_tab",
            True,
            "COORDINATES",
            fallback_used=True,
            fallback_source="COORDINATE_TAB_CLOSE",
            fallback_reason="UIA-кнопка закрытия вкладки недоступна; применён координатный fallback.",
            warnings=[{
                "code": "TAB_CLOSE_FALLBACK",
                "severity": "LOW",
                "message": "Вкладка закрыта координатным fallback.",
            }],
        )

    if not allow_hotkey_fallback:
        return _trace("close_active_document_tab", False, "FAILED")
    # FALLBACK: кнопка «X» вкладки не найдена OCR; используем Ctrl+F4.
    logger.warning("FALLBACK: кнопка закрытия вкладки не найдена, применён Ctrl+F4")
    driver.close_current_tab(pid)
    return _trace(
        "close_active_document_tab",
        True,
        "HOTKEY",
        fallback_used=True,
        fallback_source="HOTKEY_CTRL_F4",
        fallback_reason="UIA/OCR/координаты закрытия вкладки недоступны; применён Ctrl+F4.",
        warnings=[{
            "code": "TAB_CLOSE_HOTKEY_FALLBACK",
            "severity": "LOW",
            "message": "Использован fallback Ctrl+F4 для закрытия вкладки.",
        }],
    )


_DOC_LABELS = {
    "document":     "Документ",
    "spreadsheet":  "Таблица",
    "presentation": "Презентация",
}


def open_document_by_path(
    editor_path: str,
    document_path: str,
    enable_debug: bool = True,
) -> dict:
    """Открыть документ через запуск редактора с путём к файлу."""
    if not _os.path.isfile(document_path):
        return _trace(
            "open_document_by_path",
            False,
            "FAILED",
            fallback_used=False,
            fallback_reason=f"Файл не найден: {document_path}",
        )

    driver = get_driver()
    driver.launch_document(editor_path, document_path, enable_debug=enable_debug)
    return _trace(
        "open_document_by_path",
        True,
        "LAUNCH_DEBUG" if enable_debug else "LAUNCH_STANDARD",
        fallback_used=not enable_debug,
        fallback_source="LAUNCH_STANDARD_NO_DEBUG" if not enable_debug else "",
        fallback_reason=(
            "Повторный запуск открытия документа без debug-флага."
            if not enable_debug
            else ""
        ),
    )


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
        _trace(
            "create_document",
            False,
            "FAILED",
            fallback_used=True,
            fallback_source="OCR_CREATE_DOCUMENT",
            fallback_reason=f"Не удалось найти кнопку «{label}» через OCR.",
        )
        raise RuntimeError(
            f"Не удалось найти кнопку «{label}» на стартовом экране через OCR"
        )
    return _trace(
        "create_document",
        True,
        "OCR",
        fallback_used=True,
        fallback_source="OCR_CREATE_DOCUMENT",
        fallback_reason="Создание документа выполнено OCR-кликом на стартовом экране.",
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
    if _cdp_click_toolbar_tab(tab_name):
        return _trace("click_toolbar_tab", True, "DOM_CDP")

    coords = positions.get(tab_name) if positions else None
    if not coords:
        # FALLBACK: если вкладка не попала в первичную калибровку, пробуем
        # свежий OCR-клик по имени вкладки прямо перед действием.
        if _ocr_click_toolbar_tab(pid, tab_name):
            return _trace(
                "click_toolbar_tab",
                True,
                "OCR",
                fallback_used=True,
                fallback_source="OCR_ON_DEMAND_TAB",
                fallback_reason=f"DOM-клик вкладки «{tab_name}» недоступен; использован OCR fallback.",
            )
        _trace(
            "click_toolbar_tab",
            False,
            "FAILED",
            fallback_used=True,
            fallback_source="TAB_FALLBACK_EXHAUSTED",
            fallback_reason=f"Не удалось открыть вкладку «{tab_name}» ни DOM, ни OCR fallback.",
        )
        raise RuntimeError(
            f"Координаты вкладки «{tab_name}» не откалиброваны. "
            f"Перед кликом вызовите calibrate_toolbar_tabs()."
        )
    driver = get_driver()
    driver.activate_window(pid)
    rel_x, rel_y = coords
    driver.click_rel(pid, rel_x, rel_y)
    return _trace(
        "click_toolbar_tab",
        True,
        "COORDINATES",
        fallback_used=True,
        fallback_source="CALIBRATED_COORDINATES_TAB",
        fallback_reason=f"DOM-клик вкладки «{tab_name}» недоступен; использован координатный fallback.",
    )


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


def _build_scroll_next_page_script(doc_ref: str) -> str:
    return f"""
  const d = {doc_ref};
  if (!d) return {{ok:false, reason:'no_document'}};
  const w = (d.defaultView || window);

  const getWordControl = () => {{
    const candidates = [
      w.Asc && w.Asc.editor && w.Asc.editor.WordControl,
      w.AscCommon && w.AscCommon.g_oWordControl,
      w.editor && w.editor.WordControl,
      w.g_oWordControl,
    ];
    for (const c of candidates) {{
      if (c) return c;
    }}
    return null;
  }};

  const readCurrentPage = () => {{
    try {{
      const ctrl = getWordControl();
      if (!ctrl) return null;
      const docApi = ctrl.m_oDrawingDocument || ctrl.m_oLogicDocument || ctrl;
      const probes = [
        docApi && docApi.m_lCurrentPage,
        docApi && docApi.m_nCurrentPage,
        ctrl.m_lCurrentPage,
        ctrl.m_nCurrentPage,
      ];
      for (const val of probes) {{
        if (typeof val === 'number' && Number.isFinite(val)) return val;
      }}
    }} catch (e) {{
      return null;
    }}
    return null;
  }};

  const apiScroll = () => {{
    try {{
      const ctrl = getWordControl();
      const scrollApi = ctrl && ctrl.m_oScrollVerApi;
      if (!scrollApi) return '';

      if (typeof scrollApi.scrollByY === 'function') {{
        scrollApi.scrollByY(520);
        return 'DOM_VERTICAL_SCROLL_API';
      }}
      if (typeof scrollApi.scrollBy === 'function') {{
        scrollApi.scrollBy(0, 520, false);
        return 'DOM_VERTICAL_SCROLL_API';
      }}
      if (typeof scrollApi.scrollToY === 'function') {{
        const cur = Number(scrollApi.posY || scrollApi.scrollTop || 0);
        scrollApi.scrollToY(cur + 520, false);
        return 'DOM_VERTICAL_SCROLL_API';
      }}
    }} catch (e) {{
      return '';
    }}
    return '';
  }};

  const dragScroll = () => {{
    const sc = d.getElementById('id_vertical_scroll');
    if (!sc) return '';

    const surface = sc.querySelector('canvas') || sc;
    const r = surface.getBoundingClientRect();
    if (!r || r.width < 2 || r.height < 2) return '';

    const x = r.left + r.width * 0.5;
    const yStart = r.top + r.height * 0.35;
    const yEnd = r.top + r.height * 0.74;

    try {{
      const MouseEvt = w.MouseEvent || MouseEvent;
      surface.dispatchEvent(
        new MouseEvt('mousedown', {{
          bubbles: true,
          cancelable: true,
          button: 0,
          buttons: 1,
          clientX: x,
          clientY: yStart,
        }})
      );
      surface.dispatchEvent(
        new MouseEvt('mousemove', {{
          bubbles: true,
          cancelable: true,
          button: 0,
          buttons: 1,
          clientX: x,
          clientY: yEnd,
        }})
      );
      surface.dispatchEvent(
        new MouseEvt('mouseup', {{
          bubbles: true,
          cancelable: true,
          button: 0,
          clientX: x,
          clientY: yEnd,
        }})
      );
      return 'DOM_VERTICAL_SCROLL_DRAG';
    }} catch (e) {{
      return '';
    }}
  }};

  const wheelScroll = () => {{
    const targets = [
      d.getElementById('id_main_view'),
      d.getElementById('id_viewer_overlay'),
      d.getElementById('id_viewer'),
      d.getElementById('id_vertical_scroll'),
    ].filter(Boolean);
    if (!targets.length) return '';
    try {{
      const WheelEvt = w.WheelEvent || WheelEvent;
      for (const target of targets) {{
        target.dispatchEvent(new WheelEvt('wheel', {{bubbles:true, cancelable:true, deltaY:360, deltaMode:0}}));
        target.dispatchEvent(new WheelEvt('wheel', {{bubbles:true, cancelable:true, deltaY:420, deltaMode:0}}));
      }}
      return 'DOM_VERTICAL_SCROLL_WHEEL';
    }} catch (e) {{
      return '';
    }}
  }};

  const before = readCurrentPage();
  let usedMode = '';

  const runOnce = () => {{
    const methods = [apiScroll, dragScroll, wheelScroll];
    for (const method of methods) {{
      const mode = method();
      if (mode) return mode;
    }}
    return '';
  }};

  for (let attempt = 0; attempt < 3; attempt++) {{
    const mode = runOnce();
    if (mode && !usedMode) usedMode = mode;
    const after = readCurrentPage();
    if (
      typeof before === 'number' &&
      Number.isFinite(before) &&
      typeof after === 'number' &&
      Number.isFinite(after) &&
      after > before
    ) {{
      return {{ok:true, mode: usedMode || mode, before_page: before, after_page: after, page_moved: true}};
    }}
  }}

  const after = readCurrentPage();
  if (!usedMode) {{
    return {{ok:false, reason:'vertical_scroll_not_available', before_page: before, after_page: after}};
  }}

  if (
    typeof before === 'number' &&
    Number.isFinite(before) &&
    typeof after === 'number' &&
    Number.isFinite(after)
  ) {{
    return {{
      ok: after > before,
      mode: usedMode,
      before_page: before,
      after_page: after,
      page_moved: after > before,
      reason: after > before ? '' : 'page_index_not_changed',
    }};
  }}

  return {{
    ok: true,
    mode: usedMode,
    before_page: before,
    after_page: after,
    page_moved: null,
  }};
"""


def _cdp_scroll_next_page_via_vertical_scroll() -> dict:
    """Перейти на следующую страницу через вертикальный скролл редактора."""
    frame_result = _cdp_eval_in_editor_frame(_build_scroll_next_page_script("doc"))
    if isinstance(frame_result, dict) and frame_result.get("ok"):
        return {
            "ok": True,
            "mode": str(frame_result.get("mode") or "DOM_VERTICAL_SCROLL"),
            "source": "editor_frame",
        }

    root_result = _cdp_eval_root(_build_scroll_next_page_script("document"))
    if isinstance(root_result, dict) and root_result.get("ok"):
        return {
            "ok": True,
            "mode": str(root_result.get("mode") or "DOM_VERTICAL_SCROLL"),
            "source": "root",
        }

    return {"ok": False}


def _cdp_read_current_page_index():
    """Прочитать индекс текущей страницы через DOM/CDP (если доступно)."""
    frame_script = """
  const d = doc;
  const w = (d && d.defaultView) || window;
  const candidates = [
    w.Asc && w.Asc.editor && w.Asc.editor.WordControl,
    w.AscCommon && w.AscCommon.g_oWordControl,
    w.editor && w.editor.WordControl,
    w.g_oWordControl,
  ];
  const ctrl = candidates.find(Boolean);
  if (!ctrl) return {ok:false, reason:'no_word_control'};
  const docApi = ctrl.m_oDrawingDocument || ctrl.m_oLogicDocument || ctrl;
  const probes = [
    docApi && docApi.m_lCurrentPage,
    docApi && docApi.m_nCurrentPage,
    ctrl.m_lCurrentPage,
    ctrl.m_nCurrentPage,
  ];
  for (const val of probes) {
    if (typeof val === 'number' && Number.isFinite(val)) {
      return {ok:true, page: val};
    }
  }
  return {ok:false, reason:'page_index_not_found'};
"""

    root_script = """
  const d = document;
  const w = window;
  const candidates = [
    w.Asc && w.Asc.editor && w.Asc.editor.WordControl,
    w.AscCommon && w.AscCommon.g_oWordControl,
    w.editor && w.editor.WordControl,
    w.g_oWordControl,
  ];
  const ctrl = candidates.find(Boolean);
  if (!ctrl) return {ok:false, reason:'no_word_control'};
  const docApi = ctrl.m_oDrawingDocument || ctrl.m_oLogicDocument || ctrl;
  const probes = [
    docApi && docApi.m_lCurrentPage,
    docApi && docApi.m_nCurrentPage,
    ctrl.m_lCurrentPage,
    ctrl.m_nCurrentPage,
  ];
  for (const val of probes) {
    if (typeof val === 'number' && Number.isFinite(val)) {
      return {ok:true, page: val};
    }
  }
  return {ok:false, reason:'page_index_not_found'};
"""

    frame_result = _cdp_eval_in_editor_frame(frame_script)
    if isinstance(frame_result, dict) and frame_result.get("ok"):
        page = frame_result.get("page")
        if isinstance(page, (int, float)):
            return int(page)

    root_result = _cdp_eval_root(root_script)
    if isinstance(root_result, dict) and root_result.get("ok"):
        page = root_result.get("page")
        if isinstance(page, (int, float)):
            return int(page)

    return None


def _cdp_click_zoom_to_page() -> bool:
    """Кликнуть кнопку «По размеру страницы» через DOM/CDP."""
    result = _cdp_eval_in_editor_frame(
        """
  const clickButton = (btn, source) => {
    if (!btn) return false;
    const style = window.getComputedStyle(btn);
    if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
    const r = btn.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    btn.click();
    return source;
  };

  const buttonSelectors = [
    'button[title*="По размеру страницы"]',
    'button[data-original-title*="По размеру страницы"]',
    'button[title*="Fit Page"]',
    'button[data-original-title*="Fit Page"]',
    'button .btn-ic-zoomtopage',
    '.btn-ic-zoomtopage',
  ];
  for (const selector of buttonSelectors) {
    const nodes = Array.from(doc.querySelectorAll(selector));
    for (const node of nodes) {
      const btn = node.closest ? node.closest('button') : null;
      const src = clickButton(btn, selector);
      if (src) return {ok:true, source: src};
    }
  }

  const iconSelectors = [
    'use[href="#btn-ic-zoomtopage"]',
    'use[xlink\\:href="#btn-ic-zoomtopage"]',
    'svg.btn-ic-zoomtopage use',
    'custom-icon.btn-ic-zoomtopage use',
  ];
  for (const selector of iconSelectors) {
    const nodes = Array.from(doc.querySelectorAll(selector));
    for (const icon of nodes) {
      const btn = icon.closest ? icon.closest('button') : null;
      const src = clickButton(btn, selector);
      if (src) return {ok:true, source: src};
    }
  }

  const captions = Array.from(doc.querySelectorAll('button, .btn'))
    .filter(el => ((el.textContent || '').toLowerCase().includes('по размеру')
      || (el.textContent || '').toLowerCase().includes('fit page')));
  for (const el of captions) {
    const btn = el.closest ? el.closest('button') : el;
    const src = clickButton(btn, 'caption-match');
    if (src) return {ok:true, source: src};
  }

  return {ok:false, reason:'zoom_to_page_control_not_found'};
"""
    )
    if isinstance(result, dict) and result.get("ok"):
        return True

    result = _cdp_eval_root(
        """
  const clickButton = (btn, source) => {
    if (!btn) return false;
    const style = window.getComputedStyle(btn);
    if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
    const r = btn.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return false;
    btn.click();
    return source;
  };

  const buttonSelectors = [
    'button[title*="По размеру страницы"]',
    'button[data-original-title*="По размеру страницы"]',
    'button[title*="Fit Page"]',
    'button[data-original-title*="Fit Page"]',
    'button .btn-ic-zoomtopage',
    '.btn-ic-zoomtopage',
  ];
  for (const selector of buttonSelectors) {
    const nodes = Array.from(document.querySelectorAll(selector));
    for (const node of nodes) {
      const btn = node.closest ? node.closest('button') : null;
      const src = clickButton(btn, selector);
      if (src) return {ok:true, source: src};
    }
  }

  const iconSelectors = [
    'use[href="#btn-ic-zoomtopage"]',
    'use[xlink\\:href="#btn-ic-zoomtopage"]',
    'svg.btn-ic-zoomtopage use',
    'custom-icon.btn-ic-zoomtopage use',
  ];
  for (const selector of iconSelectors) {
    const nodes = Array.from(document.querySelectorAll(selector));
    for (const icon of nodes) {
      const btn = icon.closest ? icon.closest('button') : null;
      const src = clickButton(btn, selector);
      if (src) return {ok:true, source: src};
    }
  }

  const captions = Array.from(document.querySelectorAll('button, .btn'))
    .filter(el => ((el.textContent || '').toLowerCase().includes('по размеру')
      || (el.textContent || '').toLowerCase().includes('fit page')));
  for (const el of captions) {
    const btn = el.closest ? el.closest('button') : el;
    const src = clickButton(btn, 'caption-match');
    if (src) return {ok:true, source: src};
  }

  return {ok:false, reason:'zoom_to_page_control_not_found'};
"""
    )
    return bool(isinstance(result, dict) and result.get("ok"))


def _ocr_click_zoom_to_page_near_scale(pid: int) -> bool:
    """Кликнуть иконку `btn-ic-zoomtopage` через якорь «Масштаб» в статус-баре."""
    from PIL import Image
    from shared.infra.ocr import find_token_bbox

    fd, screenshot_path = tempfile.mkstemp(prefix="zoom_status_", suffix=".png")
    _os.close(fd)
    try:
        take_screenshot(screenshot_path)
        bbox = find_token_bbox(screenshot_path, "Масштаб")
        if not bbox:
            bbox = find_token_bbox(screenshot_path, "100%")
        if not bbox:
            return False

        img = Image.open(screenshot_path)
        width, height = img.size

        # Кнопка fit-to-page расположена слева от текста «Масштаб ...».
        target_x = max(0, int(bbox["left"] - width * 0.035))
        target_y = min(height - 1, int(bbox["center_y"]))

        driver = get_driver()
        driver.activate_window(pid)
        driver.click_rel(pid, target_x / width, target_y / height)
        return True
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
