#!/usr/bin/env bash
#
# install_dev_tools.sh
# Перевіряє наявність Docker, Docker Compose V2, Python >= 3.13, pip
# та ML-залежностей (torch, torchvision, pillow).
# Ідемпотентний: повторний запуск не ламає систему і не дублює дії.

set -euo pipefail

LOG_FILE="install.log"
REQUIRED_PYTHON_MAJOR=3
REQUIRED_PYTHON_MINOR=13

readonly COLOR_GREEN='\033[0;32m'
readonly COLOR_RED='\033[0;31m'
readonly COLOR_YELLOW='\033[1;33m'
readonly COLOR_RESET='\033[0m'

log() {
    local level="$1"
    local message="$2"
    local color="$COLOR_RESET"
    case "$level" in
        OK)   color="$COLOR_GREEN" ;;
        FAIL) color="$COLOR_RED" ;;
        WARN) color="$COLOR_YELLOW" ;;
    esac
    local timestamp
    timestamp="$(date '+%Y-%m-%d %H:%M:%S')"
    echo -e "${color}[${timestamp}] [${level}] ${message}${COLOR_RESET}"
    echo "[${timestamp}] [${level}] ${message}" >> "$LOG_FILE"
}

command_exists() {
    command -v "$1" &> /dev/null
}

{
    echo ""
    echo "=== Запуск install_dev_tools.sh: $(date '+%Y-%m-%d %H:%M:%S') ==="
} >> "$LOG_FILE"

log INFO "Починаємо перевірку середовища..."

check_docker() {
    if command_exists docker; then
        log OK "Docker знайдено: $(docker --version)"
    else
        log FAIL "Docker не знайдено."
        log WARN "Інструкція: https://docs.docker.com/engine/install/"
    fi
}

check_docker_compose() {
    if command_exists docker && docker compose version &> /dev/null; then
        log OK "Docker Compose V2 знайдено: $(docker compose version)"
    else
        log FAIL "Docker Compose V2 (docker compose) не знайдено."
        log WARN "Інструкція: https://docs.docker.com/compose/install/linux/"
    fi
}

check_python() {
    if ! command_exists python3; then
        log FAIL "python3 не знайдено. Встановіть Python ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}+."
        return
    fi
    local py_major py_minor
    py_major="$(python3 -c 'import sys; print(sys.version_info.major)')"
    py_minor="$(python3 -c 'import sys; print(sys.version_info.minor)')"

    if [ "$py_major" -gt "$REQUIRED_PYTHON_MAJOR" ] || \
       { [ "$py_major" -eq "$REQUIRED_PYTHON_MAJOR" ] && [ "$py_minor" -ge "$REQUIRED_PYTHON_MINOR" ]; }; then
        log OK "Python версії ${py_major}.${py_minor} відповідає вимозі (>= ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR})."
    else
        log FAIL "Знайдено Python ${py_major}.${py_minor}, потрібно >= ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}."
        log WARN "Встановіть через pyenv, deadsnakes PPA або python.org."
    fi
}

check_pip() {
    if command_exists pip3; then
        log OK "pip3 знайдено: $(pip3 --version)"
    else
        log FAIL "pip3 не знайдено."
        if command_exists python3; then
            log WARN "Спроба встановити pip через ensurepip..."
            if python3 -m ensurepip --upgrade &>> "$LOG_FILE"; then
                log OK "pip3 успішно встановлено через ensurepip."
            else
                log FAIL "Не вдалося встановити pip. Встановіть вручну."
            fi
        fi
    fi
}

check_python_package() {
    local package_name="$1"
    local import_name="$2"
    if python3 -c "import ${import_name}" &> /dev/null; then
        local pkg_version
        pkg_version="$(python3 -c "import ${import_name}; print(getattr(${import_name}, '__version__', 'unknown'))")"
        log OK "Пакет '${package_name}' знайдено (версія: ${pkg_version})."
        return 0
    else
        log FAIL "Пакет '${package_name}' не знайдено."
        return 1
    fi
}

check_ml_dependencies() {
    local all_present=true
    check_python_package "torch" "torch" || all_present=false
    check_python_package "torchvision" "torchvision" || all_present=false
    check_python_package "pillow" "PIL" || all_present=false

    if [ "$all_present" = false ]; then
        log WARN "Не всі ML-залежності присутні."
        local req_file
        req_file="$(dirname "$0")/../requirements.txt"
        if [ -f "$req_file" ]; then
            log WARN "Знайдено ${req_file}. Спроба встановити..."
            if pip3 install -r "$req_file" &>> "$LOG_FILE"; then
                log OK "Залежності успішно встановлено."
            else
                log FAIL "Не вдалося встановити автоматично. Перевірте install.log."
            fi
        else
            log WARN "requirements.txt не знайдено. Встановіть вручну: pip3 install torch torchvision pillow"
        fi
    else
        log OK "Усі ML-залежності вже присутні (ідемпотентність)."
    fi
}

main() {
    check_docker
    check_docker_compose
    check_python
    check_pip
    check_ml_dependencies
    log INFO "Перевірку завершено. Детальний лог: ${LOG_FILE}"
}

main "$@"