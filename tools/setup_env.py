"""Подготовка виртуального окружения для автотестов R7 Office.

Запуск:
    python setup_env.py

Скрипт:
1. Создаёт .venv если его нет.
2. Определяет текущую ОС.
3. Устанавливает общие + платформо-специфичные зависимости.
"""

import platform
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # Testing/
VENV_DIR = ROOT / '.venv'

REQUIREMENTS_COMMON = ROOT / 'requirements' / 'base.txt'
REQUIREMENTS_OS = {
    'Windows': ROOT / 'requirements' / 'windows.txt',
    'Linux':   ROOT / 'requirements' / 'linux.txt',
    'Darwin':  ROOT / 'requirements' / 'macos.txt',
}


def pip_path() -> str:
    if platform.system() == 'Windows':
        return str(VENV_DIR / 'Scripts' / 'pip')
    return str(VENV_DIR / 'bin' / 'pip')


def python_path() -> str:
    if platform.system() == 'Windows':
        return str(VENV_DIR / 'Scripts' / 'python')
    return str(VENV_DIR / 'bin' / 'python')


def create_venv():
    if VENV_DIR.exists():
        print(f'Окружение уже существует: {VENV_DIR}')
        return
    print(f'Создаю окружение: {VENV_DIR}')
    venv.create(str(VENV_DIR), with_pip=True)


def install_deps():
    pip = pip_path()

    if REQUIREMENTS_COMMON.exists():
        print(f'Устанавливаю общие зависимости: {REQUIREMENTS_COMMON.name}')
        subprocess.run([pip, 'install', '-r', str(REQUIREMENTS_COMMON)], check=True)

    system = platform.system()
    req_file = REQUIREMENTS_OS.get(system)
    if req_file and req_file.exists():
        print(f'Устанавливаю зависимости для {system}: {req_file.name}')
        subprocess.run([pip, 'install', '-r', str(req_file)], check=True)
    elif req_file:
        print(f'Файл {req_file.name} не найден, пропускаю платформо-специфичные зависимости.')


def verify():
    py = python_path()
    result = subprocess.run([py, '--version'], capture_output=True, text=True)
    print(f'Python в окружении: {result.stdout.strip()}')

    result = subprocess.run([py, '-c', 'import pyautogui; print("pyautogui OK")'],
                            capture_output=True, text=True)
    if result.returncode == 0:
        print(result.stdout.strip())
    else:
        print(f'Проблема с pyautogui: {result.stderr.strip()}')


if __name__ == '__main__':
    print(f'ОС: {platform.system()} {platform.release()} ({platform.machine()})')
    create_venv()
    install_deps()
    verify()
    print(f'\nОкружение готово. Запуск тестов:')
    if platform.system() == 'Windows':
        print(f'  .venv\\Scripts\\python run_all.py')
    else:
        print(f'  .venv/bin/python run_all.py')
