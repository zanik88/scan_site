# Scan Site (SaaS Audit & License Scanner)

Веб-сервис на базе **FastAPI** для аудита, анализа лицензий и проверки сайтов/компонентов с автоматической генерацией отчетов.

---

## Стек технологий

* **Backend:** Python 3.10, FastAPI, Uvicorn
* **Обработка данных и отчетов:** pandas, openpyxl, python-docx, reportlab, Jinja2
* **Контейнеризация:** Docker, Docker Compose

---

## Быстрый запуск через Docker Compose

### Требования
* Установленный [Docker](https://docs.docker.com/get-docker/) и [Docker Compose](https://docs.docker.com/compose/)

### 1. Клонирование репозитория
```bash
git clone [https://github.com/zanik88/scan_site.git](https://github.com/zanik88/scan_site.git)
cd scan_site
docker compose up --build -d
docker compose down
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000 --reload



