import asyncio
import hashlib
import io
import json
import os
import re
import secrets
from datetime import datetime

import aiohttp
import docx
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
import pandas as pd

# ReportLab для PDF
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# SQLAlchemy для базы данных
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

# --- НАСТРОЙКА БАЗЫ ДАННЫХ ---
DATABASE_URL = "sqlite:///./saas_audit.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
  __tablename__ = "users"
  id = Column(Integer, primary_key=True, index=True)
  email = Column(String, unique=True, index=True, nullable=False)
  hashed_password = Column(String, nullable=False)
  role = Column(String, default="user")
  subscription_status = Column(String, default="Free")
  created_at = Column(DateTime, default=datetime.utcnow)
  reports = relationship("AuditReport", back_populates="owner")


class AuditReport(Base):
  __tablename__ = "audit_reports"
  id = Column(Integer, primary_key=True, index=True)
  user_id = Column(Integer, ForeignKey("users.id"))
  filename = Column(String, nullable=False)
  pdf_filename = Column(String, nullable=False)
  excel_filename = Column(String, nullable=True)
  created_at = Column(DateTime, default=datetime.utcnow)
  owner = relationship("User", back_populates="reports")


Base.metadata.create_all(bind=engine)


api_description = """
Сервис для автоматизированного аудита программного обеспечения и анализа лицензий зависимостей.

**⚠️ Правовое ограничение (Disclaimer):**
Данный сервис предоставляет предварительный автоматизированный анализ лицензий и компонентов. Результаты проверки не являются окончательным правовым (юридическим) заключением. Использование сервиса не дает юридической гарантии успешного прохождения экспертизы и включения программного обеспечения в Единый реестр российских программ для ЭВМ и БД. Окончательное решение всегда остается за профильными экспертами и регулирующими органами.
"""

app = FastAPI(
    title="Reestr License SaaS - ПП РФ № 1236",
    description=api_description,
    version="1.0.0"
)

PDF_DIR = "generated_reports"
os.makedirs(PDF_DIR, exist_ok=True)

RED_LICENSES = ["GPL", "AGPL", "General Public License", "SSPL"]
GREEN_LICENSES = ["MIT", "Apache", "BSD", "ISC", "PostgreSQL License"]


# Единый блок с HTML для футера
FOOTER_HTML = """
<footer style="margin-top: 40px; padding: 20px; text-align: center; color: #7f8c8d; font-size: 12px; border-top: 1px solid #eaeaea;">
    <b>⚠️ Правовое ограничение:</b> Данный сервис предоставляет предварительный автоматизированный анализ лицензий и компонентов. 
    Результаты проверки не являются окончательным правовым (юридическим) заключением. 
    Использование сервиса не дает юридической гарантии успешного прохождения экспертизы и включения программного обеспечения в Единый реестр. 
    Окончательное решение всегда остается за профильными экспертами и регулирующими органами.
</footer>
"""

# --- ЭКСПЕРТНЫЙ СПРАВОЧНИК С УЧЕТОМ ТРЕБОВАНИЙ ПП РФ № 1236 ---
ENTERPRISE_LICENSE_DB = {
    # SAP и проприетарные корпоративные системы
    "sap": {
        "license": "SAP Proprietary EULA",
        "status": "Запрещено (Иностранное проприетарное ПО)",
        "recommendation": (
            "Проприетарное ПО под санкциями. Замените на отечественные"
            " ERP-системы (например, 1С:Предприятие)."
        ),
    },
    "sap crystal reports": {
        "license": "SAP Proprietary EULA",
        "status": "Запрещено (Иностранное проприетарное ПО)",
        "recommendation": (
            "Иностранная система отчетности. Замените на отечественные"
            " BI-системы (например, Форсайт, Visiology)."
        ),
    },
    "crystal reports": {
        "license": "SAP Proprietary EULA",
        "status": "Запрещено (Иностранное проприетарное ПО)",
        "recommendation": (
            "Иностранная система отчетности. Замените на отечественные"
            " BI-системы."
        ),
    },
    # Брокеры сообщений, очереди, базы и распределенные платформы
    "apache kafka": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": (
            "Свободная распределенная платформа обмена сообщениями"
        ),
    },
    "kafka": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": (
            "Свободный брокер сообщений под открытой лицензией Apache 2.0"
        ),
    },
    "rabbitmq": {
        "license": "MPL-2.0",
        "status": "Разрешено",
        "recommendation": (
            "Свободный брокер сообщений под лицензией Mozilla Public License"
            " 2.0"
        ),
    },
    "redis": {
        "license": "RSALv2 / SSPLv1 / BSD",
        "status": "Требует внимания (Смена лицензии)",
        "recommendation": (
            "Версии Redis 7.4+ перешли на несвободные лицензии. Рекомендуется"
            " использовать форк Valkey (BSD-3) или Redis < 7.4"
        ),
    },
    "valkey": {
        "license": "BSD-3-Clause",
        "status": "Разрешено",
        "recommendation": (
            "Свободный открытый форк Redis от Linux Foundation"
        ),
    },
    "nats": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": "Свободная легковесная система обмена сообщениями",
    },
    "activemq": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": "Свободный брокер сообщений от Apache",
    },
    "clickhouse": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": "Свободная колоночная СУБД с открытым исходным кодом",
    },
    # Вендоры и организации правообладателей
    "apache software foundation": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": (
            "Проекты фонда Apache распространяются под свободной пермиссивной"
            " лицензией Apache 2.0"
        ),
    },
    "apache software": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": "Свободное ПО под лицензией Apache License",
    },
    "epplus software": {
        "license": "PolyForm Noncommercial / Commercial",
        "status": "Требует внимания (Коммерческая лицензия)",
        "recommendation": (
            "EPPlus начиная с версии 5 требует платной коммерческой подписки."
            " Рекомендуется замена на ClosedXML"
        ),
    },
    "epplus": {
        "license": "PolyForm Noncommercial / Commercial",
        "status": "Требует внимания (Коммерческая лицензия)",
        "recommendation": (
            "EPPlus требует коммерческой лицензии, замените на ClosedXML (MIT)"
        ),
    },
    # Системы мониторинга, метрик и логирования
    "prom/prometheus": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": (
            "Свободная система сбора метрик с открытым исходным кодом"
        ),
    },
    "prometheus": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": (
            "Свободная система сбора метрик с открытым исходным кодом"
        ),
    },
    "grafana/grafana": {
        "license": "AGPL-3.0",
        "status": "Требует внимания (AGPL Copyleft)",
        "recommendation": (
            "Использует AGPLv3. Для соответствия требованиям рекомендуется"
            " изолировать в отдельный сервис или перейти на OpenSearch"
            " Dashboards"
        ),
    },
    "grafana": {
        "license": "AGPL-3.0",
        "status": "Требует внимания (AGPL Copyleft)",
        "recommendation": (
            "Использует AGPLv3. Проверьте риски раскрытия кода или используйте"
            " открытые альтернативы"
        ),
    },
    "grafana/loki": {
        "license": "AGPL-3.0",
        "status": "Требует внимания (AGPL Copyleft)",
        "recommendation": "Система логирования под лицензией AGPLv3",
    },
    "loki": {
        "license": "AGPL-3.0",
        "status": "Требует внимания (AGPL Copyleft)",
        "recommendation": "Система логирования под лицензией AGPLv3",
    },
    "victoriametrics": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": (
            "Свободная быстрая СУБД для временных рядов и метрик"
        ),
    },
    "victoria-metrics": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": (
            "Свободная СУБД для временных рядов (замена/хранилище Prometheus)"
        ),
    },
    "zabbix": {
        "license": "GPL-2.0",
        "status": "Требует внимания (GPL Copyleft)",
        "recommendation": (
            "Имеет лицензию GPLv2. Не встраивайте код Zabbix напрямую в"
            " коммерческие дистрибутивы"
        ),
    },
    "elasticsearch": {
        "license": "SSPL / Elastic License",
        "status": "Запрещено / Требует внимания",
        "recommendation": (
            "Лицензия не является свободной (SSPL). Рекомендуется перейти на"
            " OpenSearch из Реестра"
        ),
    },
    "kibana": {
        "license": "SSPL / Elastic License",
        "status": "Запрещено / Требует внимания",
        "recommendation": (
            "Лицензия SSPL не признается открытой. Замените на OpenSearch"
            " Dashboards"
        ),
    },
    "opensearch": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": (
            "Полностью свободный форк Elasticsearch под пермиссивной лицензией"
            " Apache 2.0"
        ),
    },
    "opensearch-dashboards": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": (
            "Свободный веб-интерфейс визуализации под Apache 2.0"
        ),
    },
    "jaeger": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": "Свободная система трассировки запросов (CNCF)",
    },
    "fluentd": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": (
            "Свободный сборщик и парсер логов под лицензией Apache 2.0"
        ),
    },
    "fluent-bit": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": "Свободный легковесный сборщик логов",
    },
    "monq": {
        "license": "Отечественное ПО (Реестр РФ)",
        "status": "Разрешено (Реестр РФ)",
        "recommendation": (
            "Российская платформа AIOps и зонтичного мониторинга, включена в"
            " Реестр отечественного ПО"
        ),
    },
    "datadog": {
        "license": "Иностранное проприетарное ПО",
        "status": "Запрещено (Нарушение ПП № 1236)",
        "recommendation": (
            "Иностранный облачный сервис мониторинга. Замените на"
            " Prometheus/VictoriaMetrics/Monq"
        ),
    },
    "new relic": {
        "license": "Иностранное проприетарное ПО",
        "status": "Запрещено (Нарушение ПП № 1236)",
        "recommendation": (
            "Иностранный сервис APM. Замените на открытые или отечественные"
            " решения"
        ),
    },
    "dynatrace": {
        "license": "Иностранное проприетарное ПО",
        "status": "Запрещено (Нарушение ПП № 1236)",
        "recommendation": "Иностранная проприетарная система мониторинга",
    },
    "splunk": {
        "license": "Иностранное проприетарное ПО",
        "status": "Запрещено (Нарушение ПП № 1236)",
        "recommendation": (
            "Замените на OpenSearch или отечественные SIEM/системы логирования"
        ),
    },
    # Базовые инфраструктурные компоненты и реестр
    "devexpress": {
        "license": "DevExpress Proprietary EULA / Commercial",
        "status": "Запрещено (Коммерческое проприетарное ПО)",
        "recommendation": (
            "Требует коммерческой лицензии и попадает под ограничения"
            " импортозамещения. Замените на свободные компоненты из Реестра."
        ),
    },
    "astra linux": {
        "license": "Отечественное ПО (Реестр РФ)",
        "status": "Разрешено (Доверенная ОС)",
        "recommendation": (
            "Соответствует ПП РФ № 1236, российская операционная система общего"
            " назначения"
        ),
    },
    "astra linux se": {
        "license": "Отечественное ПО (Реестр РФ)",
        "status": "Разрешено (Доверенная ОС)",
        "recommendation": (
            "Соответствует ПП РФ № 1236, российская ОС специального назначения"
        ),
    },
    "tantor": {
        "license": "Отечественное ПО (Реестр РФ)",
        "status": "Разрешено",
        "recommendation": (
            "Российская СУБД, включена в Реестр (замена Oracle/MS SQL)"
        ),
    },
    "angie pro": {
        "license": "Отечественное ПО (Реестр РФ)",
        "status": "Разрешено",
        "recommendation": (
            "Российский веб-сервер, включен в Реестр (замена Nginx)"
        ),
    },
    "angie software": {
        "license": "Отечественное ПО (Реестр РФ)",
        "status": "Разрешено",
        "recommendation": "Российский веб-сервер, включен в Реестр",
    },
    "red hat": {
        "license": "Экспортные ограничения / Иностранное ПО",
        "status": "Запрещено (Нарушение ПП № 1236)",
        "recommendation": (
            "Замените на доверенные ОС из Реестра: Astra Linux, РЕД ОС"
        ),
    },
    "centos": {
        "license": "Экспортные ограничения / Иностранное ПО",
        "status": "Запрещено (Нарушение ПП № 1236)",
        "recommendation": "Замените на российские дистрибутивы из Реестра",
    },
    "fedora": {
        "license": "Экспортные ограничения / Иностранное ПО",
        "status": "Запрещено (Нарушение ПП № 1236)",
        "recommendation": "Используйте сертифицированные ОС из Реестра",
    },
    "opensuse": {
        "license": "Экспортные ограничения / Иностранное ПО",
        "status": "Запрещено (Нарушение ПП № 1236)",
        "recommendation": "Замените на отечественные ОС",
    },
    "suse linux": {
        "license": "Экспортные ограничения / Иностранное ПО",
        "status": "Запрещено (Нарушение ПП № 1236)",
        "recommendation": "Замените на отечественные ОС",
    },
    "almalinux": {
        "license": "Экспортные ограничения / Иностранное ПО",
        "status": "Запрещено (Нарушение ПП № 1236)",
        "recommendation": "Замените на отечественные ОС из Реестра",
    },
    "rocky linux": {
        "license": "Экспортные ограничения / Иностранное ПО",
        "status": "Запрещено (Нарушение ПП № 1236)",
        "recommendation": "Замените на отечественные ОС из Реестра",
    },
    "ubuntu": {
        "license": "GPL / Ubuntu EULA",
        "status": "Разрешено",
        "recommendation": "Открытая версия разрешена к использованию",
    },
    "debian": {
        "license": "Открытая лицензия (DFSG)",
        "status": "Разрешено",
        "recommendation": (
            "Свободная операционная система с открытым исходным кодом"
        ),
    },
    "freebsd": {
        "license": "BSD",
        "status": "Разрешено",
        "recommendation": "ОС с открытой лицензией",
    },
    "openbsd": {
        "license": "BSD",
        "status": "Разрешено",
        "recommendation": "ОС с открытой лицензией",
    },
    "windows": {
        "license": "Microsoft Proprietary EULA",
        "status": "Запрещено (Иностранное проприетарное ПО)",
        "recommendation": (
            "По ПП № 1236 для гос. систем требуется применение ОС из Реестра"
        ),
    },
    "macos": {
        "license": "Apple EULA (Proprietary)",
        "status": "Запрещено (Иностранное проприетарное ПО)",
        "recommendation": (
            "Не соответствует критериям локализации и свободного обращения"
        ),
    },
    "ios": {
        "license": "Apple EULA (Proprietary)",
        "status": "Запрещено (Иностранное проприетарное ПО)",
        "recommendation": "Иностранное проприетарное ПО",
    },
    "android": {
        "license": "Apache-2.0 / Proprietary Google",
        "status": "Требует внимания",
        "recommendation": (
            "Базовый код открыт, но сервисы Google принадлежат иностранному"
            " лицу"
        ),
    },
    "visual studio code": {
        "license": "Microsoft EULA / MIT",
        "status": "Требует внимания",
        "recommendation": (
            "Рекомендуется использовать свободный форк VSCodium или"
            " отечественные среды разработки из Реестра"
        ),
    },
    "at32 ide": {
        "license": "Vendor Proprietary EULA",
        "status": "Требует внимания",
        "recommendation": (
            "Проверьте права на распространение и отсутствие преобладающего"
            " иностранного контроля"
        ),
    },
    "directx": {
        "license": "Microsoft Proprietary EULA",
        "status": "Запрещено",
        "recommendation": (
            "Используйте открытые кроссплатформенные графические API (Vulkan,"
            " OpenGL)"
        ),
    },
    "cuda": {
        "license": "NVIDIA cuDNN EULA",
        "status": "Запрещено (Иностранный компонент)",
        "recommendation": "Замените на открытые фреймворки и драйверы",
    },
    "delphi": {
        "license": "Embarcadero / Borland Proprietary",
        "status": "Запрещено (Иностранное коммерческое ПО)",
        "recommendation": "Устаревшая проприетарная среда разработки",
    },
    "borland": {
        "license": "Borland / Inprise Proprietary",
        "status": "Запрещено",
        "recommendation": (
            "Коммерческие лицензии прекратившей поддержку иностранной компании"
        ),
    },
    "arial": {
        "license": "Monotype / Microsoft Proprietary",
        "status": "Запрещено (Иностранный проприетарный шрифт)",
        "recommendation": (
            "Замените на свободные российские шрифты (например, Liberation"
            " Sans)"
        ),
    },
    "times new roman": {
        "license": "Monotype / Microsoft Proprietary",
        "status": "Запрещено (Иностранный проприетарный шрифт)",
        "recommendation": "Замените на Liberation Serif",
    },
    "calibri": {
        "license": "Microsoft Proprietary EULA",
        "status": "Запрещено (Иностранный проприетарный шрифт)",
        "recommendation": "Используйте свободные аналоги из Реестра",
    },
    "roboto": {
        "license": "SIL Open Font License (OFL)",
        "status": "Разрешено",
        "recommendation": "Свободный открытый шрифт от Google",
    },
    "oswald": {
        "license": "SIL Open Font License (OFL)",
        "status": "Разрешено",
        "recommendation": "Свободный шрифт с открытой лицензией",
    },
    "russo one": {
        "license": "SIL Open Font License (OFL)",
        "status": "Разрешено",
        "recommendation": "Свободный кириллический шрифт",
    },
    "nginx": {
        "license": "2-clause BSD",
        "status": "Разрешено",
        "recommendation": (
            "Свободный веб-сервер, или отечественный аналог Angie из Реестра"
        ),
    },
    "node.js": {
        "license": "MIT",
        "status": "Разрешено",
        "recommendation": "Свободная среда выполнения JavaScript",
    },
    "nodejs": {
        "license": "MIT",
        "status": "Разрешено",
        "recommendation": "Свободная среда выполнения JavaScript",
    },
    "express": {
        "license": "MIT",
        "status": "Разрешено",
        "recommendation": "Свободный фреймворк Node.js",
    },
    "typeorm": {
        "license": "MIT",
        "status": "Разрешено",
        "recommendation": "Свободная ORM",
    },
    "mui": {
        "license": "MIT",
        "status": "Разрешено",
        "recommendation": "Свободная библиотека UI-компонентов",
    },
    "material ui": {
        "license": "MIT",
        "status": "Разрешено",
        "recommendation": "Библиотека компонентов интерфейса",
    },
    "mobx": {
        "license": "MIT",
        "status": "Разрешено",
        "recommendation": "Свободная библиотека состояния",
    },
    "formik": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": "Свободная библиотека форм",
    },
    "babel": {
        "license": "MIT",
        "status": "Разрешено",
        "recommendation": "Свободный компилятор JS",
    },
    "date-fns": {
        "license": "MIT",
        "status": "Разрешено",
        "recommendation": "Свободная библиотека дат",
    },
    "eslint": {
        "license": "MIT",
        "status": "Разрешено",
        "recommendation": "Анализатор кода",
    },
    "postcss": {
        "license": "MIT",
        "status": "Разрешено",
        "recommendation": "Инструмент CSS",
    },
    "jackson-databind": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": "Библиотека Java",
    },
    "awssdk": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": (
            "SDK для AWS (требует использования облаков из Реестра)"
        ),
    },
    "vaultsharp": {
        "license": "MIT",
        "status": "Разрешено",
        "recommendation": "Клиент .NET",
    },
    "national instruments": {
        "license": "NI Proprietary EULA",
        "status": "Запрещено (Иностранное ПО)",
        "recommendation": (
            "Замените на отечественные измерительные комплексы из Реестра"
        ),
    },
    "extjs": {
        "license": "Sencha Commercial / GPLv3",
        "status": "Требует внимания (Коммерческая лицензия)",
        "recommendation": (
            "Требует коммерческой подписки или перехода на открытые UI-решения"
        ),
    },
    "nmap": {
        "license": "Nmap Public License (GPL-like)",
        "status": "Запрещено / Требует внимания",
        "recommendation": (
            "Имеет ограничения лицензирования, несовместимые с Реестром"
        ),
    },
    "java se": {
        "license": "Oracle Java SE Commercial / OTN",
        "status": "Требует внимания (Коммерческая Oracle)",
        "recommendation": (
            "Перейдите на свободные сборки OpenJDK (Eclipse Temurin, Liberica"
            " JDK) из Реестра"
        ),
    },
    "glitchtip": {
        "license": "MIT",
        "status": "Разрешено",
        "recommendation": "Открытая система мониторинга ошибок",
    },
    "hashicorp vault": {
        "license": "BUSL / Proprietary",
        "status": "Запрещено / Требует внимания",
        "recommendation": (
            "Используйте открытые форки (OpenBao) или отечественные решения"
        ),
    },
    "vault": {
        "license": "BUSL / Proprietary",
        "status": "Запрещено / Требует внимания",
        "recommendation": (
            "Используйте OpenBao или защищенные хранилища из Реестра"
        ),
    },
    "oracle database": {
        "license": "Проприетарная",
        "status": "Запрещено",
        "recommendation": (
            "Замените на российские СУБД из Реестра (Postgres Pro, Tantor)"
        ),
    },
    "microsoft sql": {
        "license": "Проприетарная",
        "status": "Запрещено",
        "recommendation": "Замените на PostgreSQL / PostgresPro",
    },
    "postgresql": {
        "license": "PostgreSQL License",
        "status": "Разрешено",
        "recommendation": "Рекомендуется перейти на российский аналог PostgresPro",
    },
    "wine": {
        "license": "LGPL-2.1-or-later",
        "status": "Разрешено",
        "recommendation": (
            "Свободный слой совместимости для запуска ПО под Linux"
        ),
    },
    "keycloak": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": "Свободная система управления доступом (IAM)",
    },
    "closedxml": {
        "license": "MIT",
        "status": "Разрешено",
        "recommendation": "Свободная библиотека .NET",
    },
    "exceldatareader": {
        "license": "MIT",
        "status": "Разрешено",
        "recommendation": "Свободная библиотека .NET",
    },
    "spring": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": "Свободный Java-фреймворк",
    },
    "junit": {
        "license": "Eclipse Public License 2.0",
        "status": "Разрешено",
        "recommendation": "Библиотека тестирования",
    },
    "react": {
        "license": "MIT",
        "status": "Разрешено",
        "recommendation": "Свободная библиотека UI",
    },
    "docker": {
        "license": "Apache-2.0",
        "status": "Разрешено",
        "recommendation": "Допустимо",
    },
}


def get_db():
  db = SessionLocal()
  try:
    yield db
  finally:
    db.close()


def hash_password(password: str) -> str:
  salt = secrets.token_hex(16)
  pwd_hash = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
  return f"{salt}${pwd_hash}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
  try:
    salt, pwd_hash = hashed_password.split("$")
    check_hash = hashlib.sha256(
        (plain_password + salt).encode("utf-8")
    ).hexdigest()
    return check_hash == pwd_hash
  except Exception:
    return False


# --- УМНЫЙ ПАРСЕР С ФИЛЬТРАЦИЕЙ ВЕРСИЙ И СЛУЖЕБНЫХ ДАННЫХ ---
def parse_uploaded_file(file_bytes: bytes, filename: str) -> list:
  extracted_data = []
  ext = filename.split(".")[-1].lower()

  STOP_WORDS = {
      "as", "is", "to", "be", "as is", "to be", "субд", "платная",
      "бесплатная", "nan", "none", "https", "http", "gpl", "apache",
      "mit", "sdk", "middle", "рф", "сша", "операционная", "система",
      "балансировщик", "библиотека", "веб", "tier", "компоненты/библиотеки",
      "сторонний компонент/сервис", "название лицензии", "ссылка на лицензию",
      "платная/бесплатная", "ссылка на репозиторий", "класс по", "наименование",
      "версия", "вендор", "тип лицензии", "примеры", "коммерческая",
      "коммерческая (платная)", "ссылка на файл с лицензией", 'по "название_по"',
      "2-clause bsd", "sspl", "gnu gpl, lgpl", "name", "version",
      "dependencies", "ос", "пропустят", "название", "лицензия",
      "описание", "ссылка на текс лицензии", "тип", "комментарий",
      "ссылка на текст лицензии", "операционная система",
      "системы управления базами данных", "мониторинг и наблюдаемость",
      "брокеры сообщений и координация", "хранилище данных в памяти",
      "платформа виртуализации и управления ресурсами", "контейнеризация",
      "веб-сервер, балансировщик, прокси-сервер", "инструменты для поиска и аналитики",
      "фреймворки", "библиотеки", "пакет", "the rust project developers",
      "microsoft / .net foundation", "bsd-3-clause",
  }

  STOP_SUBSTRINGS = [
      "license", "terms", "conditions", "agreement", "repository", "репозиторий",
      "соглашение", "enterprise edition", "хотим обратить ваше внимание",
      "список сторонних компонентов", "представляет собой", "написано на языках",
      "при разработке", "используются следующие", "mit or apache",
      "экспортные ограничения", "имеет экспортные",
  ]

  def is_garbage_or_version(text: str) -> bool:
    t = text.strip()
    if re.match(r"^v?[\d\.]+$", t):
      return True
    if re.match(r"^[><=~^≥≤\d\.\s]+$", t):
      return True
    if t.startswith((">", "<", "^", "~", "≥", "≤", "=")):
      return True
    if len(t) < 2 or len(t) > 45:
      return True
    if len(t.split()) > 4:
      return True
    return False

  if ext == "docx":
    try:
      doc = docx.Document(io.BytesIO(file_bytes))
      for table in doc.tables:
        for row in table.rows:
          for cell in row.cells:
            cell_text = cell.text.strip()
            if not cell_text or is_garbage_or_version(cell_text):
              continue
            if cell_text.lower() in STOP_WORDS:
              continue
            if any(sub in cell_text.lower() for sub in STOP_SUBSTRINGS):
              continue

            clean_val = cell_text.split("#")[0].strip()
            parts = re.split(r"==|>=|<=|~=|>|<", clean_val)
            pkg = parts[0].strip()
            ver = parts[1].strip() if len(parts) > 1 else "unknown"

            if not is_garbage_or_version(pkg) and pkg.lower() not in STOP_WORDS:
              extracted_data.append((pkg, ver))

      if not extracted_data:
        for p in doc.paragraphs:
          text = p.text.strip()
          if not text or is_garbage_or_version(text):
            continue
          if any(sub in text.lower() for sub in STOP_SUBSTRINGS):
            continue

          parts = re.split(r"==|>=|<=|~=|>|<", text)
          pkg = parts[0].strip()
          ver = parts[1].strip() if len(parts) > 1 else "unknown"
          if not is_garbage_or_version(pkg) and pkg.lower() not in STOP_WORDS:
            extracted_data.append((pkg, ver))
    except Exception as e:
      print(f"❌ Ошибка парсинга Word: {e}")

  elif ext in ["xlsx", "xls"]:
    try:
      excel_file = pd.ExcelFile(io.BytesIO(file_bytes))
      for sheet_name in excel_file.sheet_names:
        df = excel_file.parse(sheet_name, header=None)
        for row_idx, row in df.iterrows():
          row_values = [
              str(val).strip() for val in row.values if pd.notna(val)
          ]
          for val_str in row_values:
            val_lower = val_str.lower()
            if (
                is_garbage_or_version(val_str)
                or val_lower in STOP_WORDS
                or any(sub in val_lower for sub in STOP_SUBSTRINGS)
            ):
              continue
            if val_str.startswith("http") or val_str.startswith("www."):
              continue

            clean_val = val_str.split("#")[0].strip()
            parts = re.split(r"==|>=|<=|~=|>|<", clean_val)
            pkg = parts[0].strip()
            version = parts[1].strip() if len(parts) > 1 else "unknown"
            if not is_garbage_or_version(pkg) and pkg.lower() not in STOP_WORDS:
              extracted_data.append((pkg, version))
    except Exception as e:
      print(f"❌ Ошибка парсинга Excel: {e}")

  elif ext == "json":
    try:
      text_content = file_bytes.decode("utf-8", errors="ignore")
      data = json.loads(text_content)
      if "packages" in data:
        for pkg_path, pkg_info in data["packages"].items():
          if pkg_path == "":
            continue
          pkg_name = pkg_path.split("node_modules/")[-1]
          if pkg_name and not is_garbage_or_version(pkg_name):
            extracted_data.append((pkg_name, pkg_info.get("version", "unknown")))
      elif "dependencies" in data:
        for pkg_name, pkg_ver in data["dependencies"].items():
          if not is_garbage_or_version(pkg_name):
            extracted_data.append((
                pkg_name,
                pkg_ver.get("version", "unknown")
                if isinstance(pkg_ver, dict)
                else str(pkg_ver),
            ))
      else:
        def extract_json_recursively(obj):
          if isinstance(obj, dict):
            if "name" in obj and "version" in obj:
              p_name = str(obj["name"])
              if not is_garbage_or_version(p_name):
                extracted_data.append((p_name, str(obj["version"])))
            for k, v in obj.items():
              extract_json_recursively(v)
          elif isinstance(obj, list):
            for item in obj:
              extract_json_recursively(item)

        extract_json_recursively(data)
    except Exception as e:
      print(f"❌ Ошибка парсинга JSON: {e}")

  elif filename == "poetry.lock" or ext == "lock":
    try:
      text_content = file_bytes.decode("utf-8", errors="ignore")
      current_name, current_version = None, None
      for line in text_content.splitlines():
        line = line.strip()
        if line.startswith("[[package]]"):
          if current_name and not is_garbage_or_version(current_name):
            extracted_data.append((current_name, current_version or "unknown"))
          current_name, current_version = None, None
        elif line.startswith("name ="):
          current_name = line.split("=")[1].strip().strip("\"'")
        elif line.startswith("version ="):
          current_version = line.split("=")[1].strip().strip("\"'")
      if current_name and not is_garbage_or_version(current_name):
        extracted_data.append((current_name, current_version or "unknown"))
    except Exception as e:
      print(f"❌ Ошибка парсинга Poetry lock: {e}")

  else:
    try:
      text_content = file_bytes.decode("utf-8", errors="ignore")
      for line in text_content.splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith("-r") or line.startswith("--"):
          continue
        parts = re.split(r"==|>=|<=|~=|>|<", line)
        pkg, ver = (
            parts[0].strip(),
            parts[1].strip() if len(parts) > 1 else "unknown",
        )
        if not is_garbage_or_version(pkg) and pkg.lower() not in STOP_WORDS:
          extracted_data.append((pkg, ver))
    except Exception as e:
      print(f"❌ Ошибка текста: {e}")

  seen = set()
  unique_data = []
  for pkg, ver in extracted_data:
    pkg_key = pkg.lower()
    if pkg_key not in seen and not any(
        sub in pkg_key for sub in STOP_SUBSTRINGS
    ):
      seen.add(pkg_key)
      unique_data.append({"name": pkg, "version": ver})
  return unique_data


# --- УМНЫЙ ПОИСК С ТОЧНЫМ СОПОСТАВЛЕНИЕМ ---
async def fetch_package_info_with_version(
    session: aiohttp.ClientSession, package_name: str, table_version: str
) -> dict:
  pkg_lower = package_name.lower().strip()
  clean_search_name = re.sub(r"\(.*?\)", "", pkg_lower).strip()
  name_without_versions = re.sub(
      r"\b\d+(\.\d+)*\b", "", clean_search_name
  ).strip()
  short_docker_name = (
      clean_search_name.split("/")[-1].strip()
      if "/" in clean_search_name
      else clean_search_name
  )

  sorted_keys = sorted(ENTERPRISE_LICENSE_DB.keys(), key=len, reverse=True)
  matched_item = None

  for key in sorted_keys:
    key_parts = key.split()
    if (
        key == clean_search_name
        or key == short_docker_name
        or key == name_without_versions
        or key in clean_search_name
        or key in name_without_versions
        or (
            len(key_parts) > 1
            and all(part in name_without_versions for part in key_parts)
        )
    ):
      if key == "express" and "devexpress" in clean_search_name:
        continue
      matched_item = ENTERPRISE_LICENSE_DB[key]
      break

  if matched_item:
    extracted_ver = table_version
    if extracted_ver == "unknown":
      ver_match = re.search(r"([\d\.]+)", clean_search_name)
      extracted_ver = ver_match.group(1).strip(".") if ver_match else "stable"

    status_text = matched_item["status"]
    if "recommendation" in matched_item:
      status_text += (
          " <br><small style='color: #e67e22;'>💡"
          f" <i>{matched_item['recommendation']}</i></small>"
      )

    return {
        "name": package_name,
        "version": extracted_ver,
        "license": (
            "<a href='https://reestr.digital.gov.ru/help/' target='_blank'"
            " style='color: #2980b9; text-decoration:"
            f" underline;'>{matched_item['license']}</a>"
        ),
        "status": status_text,
    }

  parts_list = name_without_versions.split()
  if not parts_list:
    return {
        "name": package_name,
        "version": table_version,
        "license": "Не найдено",
        "status": "Требует ручной проверки",
    }

  clean_pypi_name = parts_list[0].strip()
  url = f"https://pypi.org/pypi/{clean_pypi_name}/json"

  try:
    async with session.get(url, timeout=4) as response:
      if response.status != 200:
        return {
            "name": package_name,
            "version": table_version,
            "license": "Не найдено в сети",
            "status": "Требует ручной проверки",
        }

      data = await response.json()
      info = data.get("info", {})
      final_version = (
          table_version
          if table_version != "unknown"
          else info.get("version", "unknown")
      )

      possible_license_strings = []
      if info.get("license_expression"):
        possible_license_strings.append(str(info.get("license_expression")))
      raw_license = info.get("license")
      if isinstance(raw_license, str):
        possible_license_strings.append(raw_license)
      elif isinstance(raw_license, dict):
        possible_license_strings.append(raw_license.get("text", ""))

      classifiers = info.get("classifiers") or []
      possible_license_strings.extend(
          [c.split("::")[-1].strip() for c in classifiers if "License ::" in c]
      )

      valid_strings = [
          s.strip()
          for s in possible_license_strings
          if s and s.strip().lower() not in ["none", "unknown", ""]
      ]
      extracted_license = (
          min(valid_strings, key=len)[:37] + "..."
          if valid_strings
          else "Unknown"
      )

      status = (
          "Требует ручной проверки"
          if extracted_license == "Unknown"
          else "Разрешено"
      )
      if extracted_license != "Unknown":
        if any(red.lower() in extracted_license.lower() for red in RED_LICENSES):
          status = "Запрещено (Copyleft / SSPL риск)"
        elif any(
            green.lower() in extracted_license.lower() for green in GREEN_LICENSES
        ):
          status = "Разрешено"

      return {
          "name": package_name,
          "version": final_version,
          "license": (
              f"<a href='{info.get('package_url', '')}' target='_blank'"
              " style='color: #2980b9; text-decoration:"
              f" underline;'>{extracted_license}</a>"
          ),
          "status": status,
      }
  except Exception:
    return {
        "name": package_name,
        "version": table_version,
        "license": "Ошибка сети",
        "status": "Требует ручной проверки",
    }


async def analyze_dependencies(file_bytes: bytes, filename: str):
  parsed_items = parse_uploaded_file(file_bytes, filename)
  if not parsed_items:
    return []
  async with aiohttp.ClientSession() as session:
    tasks = [
        fetch_package_info_with_version(
            session, item["name"], item["version"]
        )
        for item in parsed_items
    ]
    return await asyncio.gather(*tasks)


# --- ГЕНЕРАЦИЯ ОТЧЕТОВ ---
def generate_pdf_report(report_data: list, filename: str) -> str:
  filepath = os.path.join(PDF_DIR, filename)
  doc = SimpleDocTemplate(
      filepath,
      pagesize=A4,
      rightMargin=30,
      leftMargin=30,
      topMargin=30,
      bottomMargin=30,
  )
  elements = []

  font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
  font_name = "DejaVuSans" if os.path.exists(font_path) else "Helvetica"
  
  if font_name == "DejaVuSans":
      pdfmetrics.registerFont(TTFont("DejaVuSans", font_path))

  styles = getSampleStyleSheet()
  title_style = ParagraphStyle(
      "TitleStyle",
      parent=styles["Heading1"],
      fontName=font_name,
      fontSize=18,
      textColor=colors.HexColor("#2c3e50"),
      spaceAfter=15,
  )
  normal_style = ParagraphStyle(
      "NormalStyle",
      parent=styles["Normal"],
      fontName=font_name,
      fontSize=10,
      textColor=colors.HexColor("#333333"),
  )
  disclaimer_style = ParagraphStyle(
      "DisclaimerStyle",
      parent=styles["Normal"],
      fontName=font_name,
      fontSize=9,
      textColor=colors.HexColor("#7f8c8d"),
      leading=11,
      spaceBefore=20,
  )
  cell_style = ParagraphStyle(
      "CellStyle",
      parent=styles["Normal"],
      fontName=font_name,
      fontSize=9,
      textColor=colors.HexColor("#333333"),
      leading=11,
  )
  header_style = ParagraphStyle(
      "HeaderStyle",
      parent=styles["Normal"],
      fontName=font_name,
      fontSize=9,
      textColor=colors.whitesmoke,
      leading=11,
  )

  elements.append(
      Paragraph(
          "<b>ОТЧЕТ ОБ АУДИТЕ ЛИЦЕНЗИЙ ПО (ПП РФ № 1236)</b>", title_style
      )
  )
  elements.append(
      Paragraph(
          "Проверка компонентов ПО на соответствие требованиям Реестра"
          " отечественного ПО.",
          normal_style,
      )
  )
  elements.append(Spacer(1, 15))

  table_rows = [[
      Paragraph("<b>Компонент (версия)</b>", header_style),
      Paragraph("<b>Обнаруженная лицензия</b>", header_style),
      Paragraph("<b>Статус для Реестра</b>", header_style),
  ]]
  for item in report_data:
    table_rows.append([
        Paragraph(
            f"{item['name']} (v.{item.get('version')})", cell_style
        ),
        Paragraph(re.sub("<[^<]+?>", "", item["license"]), cell_style),
        Paragraph(re.sub("<[^<]+?>", "", item["status"]), cell_style),
    ])

  t = Table(table_rows, colWidths=[150, 200, 185])
  t.setStyle(
      TableStyle([
          ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
          ("FONTNAME", (0, 0), (-1, -1), font_name),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
          ("TOPPADDING", (0, 0), (-1, -1), 6),
          ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
          (
              "ROWBACKGROUNDS",
              (0, 1),
              (-1, -1),
              [colors.white, colors.HexColor("#f9f9f9")],
          ),
      ])
  )
  elements.append(t)

  # ДОБАВЛЕНО: Правовой дисклеймер в PDF отчет
  elements.append(
      Paragraph(
          "<b>Внимание:</b> Данный отчет предоставляет предварительный автоматизированный анализ лицензий и компонентов. "
          "Результаты проверки не являются окончательным правовым (юридическим) заключением. "
          "Использование сервиса не дает юридической гарантии успешного прохождения экспертизы и включения программного обеспечения в Единый реестр.",
          disclaimer_style
      )
  )

  doc.build(elements)
  return filepath


def generate_excel_report(report_data: list, filename: str) -> str:
  filepath = os.path.join(PDF_DIR, filename)
  df = pd.DataFrame([{
      "Компонент": item["name"],
      "Версия": item.get("version", "unknown"),
      "Обнаруженная лицензия": re.sub(r"<[^<]+?>", "", item["license"]),
      "Статус для Реестра": re.sub(r"<[^<]+?>", "", item["status"]),
  } for item in report_data])
  df.to_excel(filepath, index=False, engine="openpyxl")
  return filepath


# --- МАРШРУТЫ И ИНТЕРФЕЙС ---
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
  user_email = request.cookies.get("user_email")
  user = (
      db.query(User).filter(User.email == user_email).first()
      if user_email
      else None
  )

  guest_count = int(request.cookies.get("guest_audit_count", 0))
  checks_left = max(0, 2 - guest_count)

  guest_info_html = (
      "<div style='background: #fff3cd; color: #856404; padding: 10px 15px;"
      " border-radius: 8px; margin-bottom: 20px; font-size: 14px;'>⚠️ Вы в"
      f" демо-режиме. Осталось бесплатных проверок: <b>{checks_left}/2</b></div>"
      if not user
      else ""
  )

  if user:
    admin_link = (
        " | <a href='/admin' style='color: #e74c3c; font-weight:bold;"
        " text-decoration: none;'>👑 Админка</a>"
        if user.role == "admin"
        else ""
    )
    user_bar_html = (
        f"<span style='font-size: 14px; color: #555;'>👤 <b>{user.email}</b></span>"
        f" <a href='/dashboard' class='nav-btn nav-btn-primary'>Кабинет</a>{admin_link}"
        " <a href='/logout' class='nav-btn nav-btn-secondary'>Выйти</a>"
    )
  else:
    user_bar_html = (
        "<a href='/login' class='nav-btn nav-btn-primary'>Войти</a> <a"
        " href='/register' class='nav-btn nav-btn-secondary'>Регистрация</a>"
    )

  html_content = f"""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>Аудит лицензий ПО по ПП РФ № 1236</title>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 850px; margin: 40px auto; padding: 0 20px; background: #f4f7f6; color: #333; display: flex; flex-direction: column; min-height: 90vh; }}
            .content {{ flex: 1; }}
            .card {{ background: white; padding: 35px; border-radius: 14px; box-shadow: 0 4px 15px rgba(0,0,0,0.06); }}
            .header-flex {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; gap: 20px; flex-wrap: wrap; }}
            h1 {{ color: #2c3e50; font-size: 24px; margin: 0; line-height: 1.3; }}
            .auth-buttons {{ display: flex; align-items: center; gap: 10px; white-space: nowrap; }}

            .nav-btn {{ padding: 8px 18px; font-size: 14px; font-weight: 600; border-radius: 20px; text-decoration: none; display: inline-block; transition: background 0.2s; }}
            .nav-btn-primary {{ background: #3498db; color: white; }}
            .nav-btn-primary:hover {{ background: #2980b9; }}
            .nav-btn-secondary {{ background: #95a5a6; color: white; }}
            .nav-btn-secondary:hover {{ background: #7f8c8d; }}

            input[type=file] {{
                margin: 20px 0;
                padding: 14px;
                border: 2px dashed #3498db;
                border-radius: 10px;
                width: 100%;
                box-sizing: border-box;
                background: #f8fafc;
                font-size: 15px;
                cursor: pointer;
            }}
            input[type=file]::file-selector-button {{
                background: #3498db;
                color: white;
                border: none;
                padding: 10px 20px;
                font-size: 15px;
                font-weight: bold;
                border-radius: 8px;
                cursor: pointer;
                margin-right: 15px;
                transition: background 0.2s;
            }}
            input[type=file]::file-selector-button:hover {{
                background: #2980b9;
            }}

            .submit-btn {{ background: #27ae60; color: white; border: none; padding: 12px 28px; font-size: 16px; font-weight: bold; border-radius: 25px; cursor: pointer; transition: background 0.2s; display: inline-block; margin-top: 10px; }}
            .submit-btn:hover {{ background: #219653; }}
            .formats {{ font-size: 13px; color: #666; margin-top: 5px; }}
            p {{ color: #555; line-height: 1.5; }}
        </style>
    </head>
    <body>
        <div class="content">
            <div class="card">
                <div class="header-flex">
                    <h1>🛡️ SaaS Аудит Лицензий<br><span style="font-size: 16px; font-weight: normal; color: #666;">Соответствие правилам ПП РФ № 1236</span></h1>
                    <div class="auth-buttons">
                        {user_bar_html}
                    </div>
                </div>
                {guest_info_html}
                <p>Загрузите файл с компонентами вашего проекта (манифест зависимостей или выгрузку) для автоматической проверки лицензий и рисков импортозамещения.</p>
                <form action="/upload" method="post" enctype="multipart/form-data">
                    <input type="file" name="file" accept=".txt,.xlsx,.xls,.json,.lock,.docx" required>
                    <div class="formats">Поддерживаемые форматы: <b>.txt</b>, <b>.xlsx / .xls</b>, <b>.json</b>, <b>.lock</b>, <b>.docx</b></div>
                    <br>
                    <button type="submit" class="submit-btn">🚀 Начать аудит</button>
                </form>
            </div>
        </div>
        {FOOTER_HTML}
    </body>
    </html>
    """
  return HTMLResponse(content=html_content)


@app.get("/register", response_class=HTMLResponse)
async def register_page():
  return HTMLResponse(content="""
    <!DOCTYPE html>
    <html lang="ru"><head><meta charset="UTF-8"><title>Регистрация</title>
    <style>body { font-family: Arial; max-width: 400px; margin: 80px auto; padding: 20px; background: #f4f7f6; }
    .card { background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
    input { width: 100%; padding: 10px; margin: 10px 0; box-sizing: border-box; border: 1px solid #ddd; border-radius: 8px; }
    button { background: #27ae60; color: white; border: none; padding: 10px; width: 100%; border-radius: 20px; cursor: pointer; font-size: 16px; }</style></head>
    <body><div class="card"><h2>Регистрация</h2>
    <form action="/register" method="post">
        <input type="email" name="email" placeholder="Email" required>
        <input type="password" name="password" placeholder="Пароль" required>
        <button type="submit">Зарегистрироваться</button>
    </form>
    <p><a href="/">← На главную</a></p></div></body></html>
    """)


@app.post("/register")
async def register(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
  if db.query(User).filter(User.email == email).first():
    raise HTTPException(status_code=400, detail="Email уже занят")
  assigned_role = "admin" if db.query(User).count() == 0 else "user"
  db.add(
      User(
          email=email,
          hashed_password=hash_password(password),
          role=assigned_role,
      )
  )
  db.commit()
  return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/login", response_class=HTMLResponse)
async def login_page():
  return HTMLResponse(content="""
    <!DOCTYPE html>
    <html lang="ru"><head><meta charset="UTF-8"><title>Вход</title>
    <style>body { font-family: Arial; max-width: 400px; margin: 80px auto; padding: 20px; background: #f4f7f6; }
    .card { background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
    input { width: 100%; padding: 10px; margin: 10px 0; box-sizing: border-box; border: 1px solid #ddd; border-radius: 8px; }
    button { background: #3498db; color: white; border: none; padding: 10px; width: 100%; border-radius: 20px; cursor: pointer; font-size: 16px; }</style></head>
    <body><div class="card"><h2>Вход</h2>
    <form action="/login" method="post">
        <input type="email" name="email" placeholder="Email" required>
        <input type="password" name="password" placeholder="Пароль" required>
        <button type="submit">Войти</button>
    </form>
    <p><a href="/">← На главную</a></p></div></body></html>
    """)


@app.post("/login")
async def login(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
  user = db.query(User).filter(User.email == email).first()
  if not user or not verify_password(password, user.hashed_password):
    raise HTTPException(status_code=400, detail="Неверный email или пароль")
  response = RedirectResponse(
      url="/dashboard", status_code=status.HTTP_303_SEE_OTHER
  )
  response.set_cookie(key="user_email", value=user.email)
  return response


@app.get("/logout")
async def logout():
  response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
  response.delete_cookie(key="user_email")
  return response


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    user_email = request.cookies.get("user_email")
    if not user_email:
        return RedirectResponse(url="/login")
    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        return RedirectResponse(url="/login")
        
    reports = db.query(AuditReport).filter(AuditReport.user_id == user.id).all()

    is_admin = user.role == "admin"

    rows = []
    for r in reports:
        del_btn = ""
        if is_admin:
            del_btn = (
                f"<td><form method='POST' action='/reports/delete/{r.id}' "
                f"onsubmit=\"return confirm('Удалить эту запись?');\" style='margin:0;'>"
                f"<button type='submit' style='background:none; border:none; color:#e74c3c; "
                f"cursor:pointer; font-weight:bold; text-decoration:underline;'>Удалить</button>"
                f"</form></td>"
            )

        rows.append(
            f"<tr><td>{r.filename}</td><td>{r.created_at.strftime('%Y-%m-%d %H:%M')}</td>"
            f"<td><a href='/download/{r.pdf_filename}'>Скачать PDF</a></td>"
            f"<td><a href='/download_excel/{r.excel_filename}'>Скачать Excel</a></td>"
            f"{del_btn}</tr>"
        )

    report_rows = "".join(rows)

    admin_btn = (
        '<a href="/admin" class="btn" style="background: #e74c3c; margin-left: 10px;">👑 Админ-панель</a>'
        if is_admin
        else ""
    )

    action_header = "<th>Действие</th>" if is_admin else ""
    empty_colspan = "5" if is_admin else "4"

    html_content = f"""
<!DOCTYPE html>
<html lang="ru"><head><meta charset="UTF-8"><title>Личный кабинет</title>
<style>body {{ font-family: Arial; max-width: 900px; margin: 40px auto; padding: 0 20px; background: #f4f7f6; display: flex; flex-direction: column; min-height: 90vh; }}
.content {{ flex: 1; }}
.card {{ background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
th, td {{ padding: 12px; border-bottom: 1px solid #ddd; text-align: left; }}
th {{ background: #2c3e50; color: white; }}
.btn {{ background: #3498db; color: white; padding: 8px 16px; text-decoration: none; border-radius: 20px; display: inline-block; margin-top: 20px; transition: background 0.2s; }}
.btn:hover {{ background: #2980b9; }}
</style></head>
<body>
<div class="content">
<div class="card">
<h2>Личный кабинет</h2>
<p><b>Email:</b> {user.email} (Роль: <i>{user.role}</i>)</p>
<p><b>Статус подписки:</b> <span style="color: green;">{user.subscription_status}</span></p>
<h3>История ваших проверок</h3>
<table><tr><th>Файл</th><th>Дата</th><th>PDF Отчет</th><th>Excel Отчет</th>{action_header}</tr>{report_rows if report_rows else f"<tr><td colspan='{empty_colspan}'>История пуста</td></tr>"}</table>
<br><a href="/" class="btn">← На главную</a><a href="/logout" class="btn" style="background: #7f8c8d; margin-left: 10px;">Выйти</a>{admin_btn}
</div>
</div>
{FOOTER_HTML}
</body></html>
"""
    return HTMLResponse(content=html_content)


@app.post("/reports/delete/{report_id}")
async def delete_report(report_id: int, request: Request, db: Session = Depends(get_db)):
    user_email = request.cookies.get("user_email")
    if not user_email:
        return RedirectResponse(url="/login")
        
    user = db.query(User).filter(User.email == user_email).first()
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Недостаточно прав для удаления отчета")

    report = db.query(AuditReport).filter(AuditReport.id == report_id).first()
    if report:
        for fname in [report.pdf_filename, report.excel_filename]:
            if fname:
                filepath = os.path.join("generated_reports", fname)
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except OSError:
                        pass
        db.delete(report)
        db.commit()

    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


# --- АДМИН-ПАНЕЛЬ ---
@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, db: Session = Depends(get_db)):
  user_email = request.cookies.get("user_email")
  if not user_email:
    return RedirectResponse(url="/login")
  user = db.query(User).filter(User.email == user_email).first()

  if not user or user.role != "admin":
    return HTMLResponse(
        "<div style='text-align:center; font-family:Arial;"
        " margin-top:50px;'><h1 style='color:red;'>403 Ошибка Доступа</h1><a"
        " href='/'>Вернуться на главную</a></div>",
        status_code=403,
    )

  all_users = db.query(User).all()
  all_reports = db.query(AuditReport).all()

  users_html = ""
  for u in all_users:
    reset_form = f"""
        <form action='/admin/reset_password' method='post' style='margin:0; display:flex; gap:5px;'>
            <input type='hidden' name='user_id' value='{u.id}'>
            <input type='text' name='new_password' placeholder='Новый пароль' required style='padding:4px; width:100px;'>
            <button type='submit' style='background:#e67e22; color:white; border:none; border-radius:4px; cursor:pointer;'>Сбросить</button>
        </form>
        """
    users_html += (
        f"<tr><td>{u.id}</td><td>{u.email}</td><td><b>{u.role}</b></td><td>{reset_form}</td></tr>"
    )

  reports_html = "".join([
      f"<tr><td>{r.id}</td><td>{r.owner.email if r.owner else 'Удален'}</td><td>{r.filename}</td><td>{r.created_at.strftime('%Y-%m-%d %H:%M')}</td><td><a"
      f" href='/download/{r.pdf_filename}'>PDF</a></td><td><form method='POST' action='/reports/delete/{r.id}' onsubmit='return confirm(&#39;Удалить этот отчет навсегда?&#39;);' style='margin:0;'><button type='submit' style='background:none;border:none;color:#e74c3c;cursor:pointer;font-weight:bold;text-decoration:underline;'>Удалить</button></form></td></tr>"
      for r in all_reports
  ])

  html_content = f"""
    <!DOCTYPE html>
    <html lang="ru"><head><meta charset="UTF-8"><title>Панель администратора</title>
    <style>
        body {{ font-family: Arial; max-width: 1000px; margin: 40px auto; padding: 0 20px; background: #f4f7f6; display: flex; flex-direction: column; min-height: 90vh; }}
        .content {{ flex: 1; }}
        .card {{ background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px; }}
        th, td {{ padding: 10px; border-bottom: 1px solid #ddd; text-align: left; }}
        th {{ background: #2c3e50; color: white; }}
        .btn {{ background: #3498db; color: white; padding: 8px 16px; text-decoration: none; border-radius: 20px; display: inline-block; transition: background 0.2s; }}
    </style></head>
    <body>
        <div class="content">
            <div class="card">
                <h2>👑 Панель управления системой</h2>
                <a href="/" class="btn">← На главную</a><a href="/dashboard" class="btn" style="background: #7f8c8d; margin-left: 10px;">Личный кабинет</a>
            </div>
            <div class="card">
                <h3>Пользователи и сброс паролей (Всего: {len(all_users)})</h3>
                <table><tr><th>ID</th><th>Email</th><th>Роль</th><th>Смена пароля</th></tr>{users_html if users_html else "<tr><td colspan='4'>Нет данных</td></tr>"}</table>
            </div>
            <div class="card">
                <h3>Все созданные отчеты (Всего: {len(all_reports)})</h3>
                <table><tr><th>ID</th><th>Владелец</th><th>Оригинальный файл</th><th>Дата проверки</th><th>Скачать</th><th>Действие</th></tr>{reports_html if reports_html else "<tr><td colspan='5'>Нет данных</td></tr>"}</table>
            </div>
        </div>
        {FOOTER_HTML}
    </body></html>
    """
  return HTMLResponse(content=html_content)


@app.post("/admin/reset_password")
async def admin_reset_password(
    request: Request,
    user_id: int = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db),
):
  admin_email = request.cookies.get("user_email")
  if not admin_email:
    raise HTTPException(status_code=403, detail="Не авторизован")

  admin_user = db.query(User).filter(User.email == admin_email).first()
  if not admin_user or admin_user.role != "admin":
    raise HTTPException(status_code=403, detail="Доступ запрещен")

  target_user = db.query(User).filter(User.id == user_id).first()
  if not target_user:
    raise HTTPException(status_code=404, detail="Пользователь не найден")

  target_user.hashed_password = hash_password(new_password)
  db.commit()
  return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/upload", response_class=HTMLResponse)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
  user_email = request.cookies.get("user_email")
  user = (
      db.query(User).filter(User.email == user_email).first()
      if user_email
      else None
  )

  guest_count = int(request.cookies.get("guest_audit_count", 0))
  if not user and guest_count >= 2:
    return HTMLResponse(
        """
        <div style='text-align:center; font-family:Arial; margin-top:100px;'>
            <h1 style='color:#e74c3c;'>⚠️ Лимит исчерпан</h1>
            <p style='font-size: 18px;'>В демо-режиме доступно только 2 проверки.</p>
            <a href='/register' style='padding: 12px 25px; background: #27ae60; color: white; text-decoration: none; border-radius: 25px; font-size: 16px; display: inline-block; margin-top: 15px;'>Зарегистрироваться бесплатно</a>
            <br><br><br><a href='/' style='color: #7f8c8d; text-decoration: none;'>← Вернуться на главную</a>
        </div>
        """,
        status_code=403,
    )

  file_bytes = await file.read()
  report = await analyze_dependencies(file_bytes, file.filename)
  total_count = len(report)

  demo_banner = ""
  if not user and total_count > 3:
    report = report[:3]
    report.append({
        "name": f"⚠️ Скрыто еще {total_count - 3} компонентов",
        "version": "???",
        "license": "<b>Зарегистрируйтесь, чтобы увидеть полный отчет</b>",
        "status": "Требует регистрации",
    })
    demo_banner = (
        "<div style='background: #fef5e7; border-left: 5px solid #d35400;"
        " padding: 15px; margin-bottom: 20px; border-radius: 0 8px 8px 0;'><b"
        " style='color: #d35400;'>Внимание:</b> Показан неполный отчет."
        " Пожалуйста, <a href='/register'>зарегистрируйтесь</a>, чтобы увидеть"
        " весь список компонентов.</div>"
    )

  timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
  base_name = file.filename.split(".")[0]
  pdf_filename, excel_filename = (
      f"audit_{timestamp}_{base_name}.pdf",
      f"audit_{timestamp}_{base_name}.xlsx",
  )

  generate_pdf_report(report, pdf_filename)
  generate_excel_report(report, excel_filename)

  if user:
    db.add(
        AuditReport(
            user_id=user.id,
            filename=file.filename,
            pdf_filename=pdf_filename,
            excel_filename=excel_filename,
        )
    )
    db.commit()

  safe_count = sum(1 for item in report if "Разрешено" in item["status"])
  danger_count = sum(1 for item in report if "Запрещено" in item["status"])
  warn_count = len(report) - safe_count - danger_count

  rows = ""
  for item in report:
    st = item["status"]
    if "Разрешено" in st:
      status_class, cat = "safe", "safe"
    elif "Запрещено" in st:
      status_class, cat = "danger", "danger"
    else:
      status_class, cat = "warn", "warn"
    rows += (
        f"<tr data-category='{cat}'><td><b>{item['name']}</b>"
        f" (v.{item.get('version')})</td><td>{item['license']}</td><td"
        f" class='{status_class}'>{st}</td></tr>"
    )

  html_content = f"""
    <!DOCTYPE html>
    <html lang="ru"><head><meta charset="UTF-8"><title>Результаты аудита (ПП РФ № 1236)</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            body {{ font-family: Arial, sans-serif; max-width: 950px; margin: 40px auto; padding: 0 20px; background: #f4f7f6; color: #333; position: relative; display: flex; flex-direction: column; min-height: 90vh; }}
            .content {{ flex: 1; }}
            .card {{ background: white; padding: 30px; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); margin-bottom: 20px; }}
            .stats-container {{ display: flex; align-items: center; justify-content: space-around; flex-wrap: wrap; margin-bottom: 20px; }}
            .chart-box {{ width: 280px; height: 280px; }}
            .stat-cards {{ display: flex; flex-direction: column; gap: 10px; }}
            .stat-badge {{ padding: 10px 15px; border-radius: 8px; font-weight: bold; font-size: 14px; cursor: pointer; transition: transform 0.1s, box-shadow 0.1s; user-select: none; }}
            .stat-badge:hover {{ transform: translateY(-2px); box-shadow: 0 4px 8px rgba(0,0,0,0.1); }}
            .badge-safe {{ background: #e8f8f5; color: #27ae60; border-left: 5px solid #27ae60; }}
            .badge-danger {{ background: #fdedec; color: #c0392b; border-left: 5px solid #c0392b; }}
            .badge-warn {{ background: #fef5e7; color: #d35400; border-left: 5px solid #d35400; }}
            .badge-reset {{ background: #ecf0f1; color: #2c3e50; border-left: 5px solid #7f8c8d; text-align: center; font-size: 13px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ padding: 12px; border-bottom: 1px solid #ddd; text-align: left; }}
            th {{ background: #2c3e50; color: white; }}
            .safe {{ color: #27ae60; font-weight: bold; }} .danger {{ color: #c0392b; font-weight: bold; }} .warn {{ color: #d35400; font-weight: bold; }}
            .btn {{ display: inline-block; margin-top: 15px; text-decoration: none; background: #3498db; color: white; padding: 10px 18px; border-radius: 20px; transition: background 0.2s; }}
            .btn:hover {{ background: #2980b9; }}
            
            .back-to-top {{
                position: fixed;
                bottom: 30px;
                right: 30px;
                width: 45px;
                height: 45px;
                background: #2c3e50;
                color: white;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                text-decoration: none;
                font-size: 22px;
                font-weight: bold;
                box-shadow: 0 4px 12px rgba(0,0,0,0.2);
                transition: opacity 0.3s, background 0.2s, transform 0.2s;
                opacity: 0;
                visibility: hidden;
                z-index: 1000;
            }}
            .back-to-top.show {{
                opacity: 1;
                visibility: visible;
            }}
            .back-to-top:hover {{
                background: #34495e;
                transform: translateY(-3px);
            }}
        </style>
    </head>
    <body>
        <div class="content">
            <div class="card">
                <div style='margin-bottom: 20px;'><a href='/' style='background: #3498db; color: white; padding: 8px 16px; text-decoration: none; border-radius: 20px; display: inline-block; font-size: 14px; margin-right: 10px;'>← На главную</a><a href='/dashboard' style='background: #7f8c8d; color: white; padding: 8px 16px; text-decoration: none; border-radius: 20px; display: inline-block; font-size: 14px;'>Личный кабинет</a></div>
                <h1>📊 Результаты аудита (ПП РФ № 1236)</h1>
                {demo_banner}
                <p>Проанализировано компонентов: <b>{total_count if user else "Более 3"}</b></p>
                <div class="stats-container">
                    <div class="chart-box"><canvas id="auditChart"></canvas></div>
                    <div class="stat-cards">
                        <div class="stat-badge badge-safe" onclick="filterRows('safe')">✅ Разрешено / Реестр: {safe_count}</div>
                        <div class="stat-badge badge-danger" onclick="filterRows('danger')">❌ Нарушения / Риски: {danger_count}</div>
                        <div class="stat-badge badge-warn" onclick="filterRows('warn')">⚠️ Требует внимания: {warn_count}</div>
                        <div class="stat-badge badge-reset" onclick="filterRows('all')">🔄 Сбросить фильтр</div>
                    </div>
                </div>
                <script>
                    const ctx = document.getElementById('auditChart').getContext('2d');
                    new Chart(ctx, {{
                        type: 'doughnut',
                        data: {{ labels: ['Разрешено', 'Запрещено', 'Внимание / Скрыто'], datasets: [{{ data: [{safe_count}, {danger_count}, {warn_count}], backgroundColor: ['#27ae60', '#c0392b', '#d35400'], borderWidth: 2 }}] }},
                        options: {{ responsive: true, plugins: {{ legend: {{ position: 'bottom' }} }} }}
                    }});
                    function filterRows(category) {{
                        document.querySelectorAll('tr[data-category]').forEach(row => {{ row.style.display = (category === 'all' || row.getAttribute('data-category') === category) ? '' : 'none'; }});
                    }}
                </script>
            </div>
            <div class="card">
                <h3>Детальный список компонентов</h3>
                <table><thead><tr><th>Компонент</th><th>Лицензия и основание</th><th>Статус (ПП РФ № 1236)</th></tr></thead><tbody>{rows}</tbody></table><br>
                <a href="/download/{pdf_filename}" class="btn">📥 Скачать официальный PDF-отчет</a>
                <a href="/download_excel/{excel_filename}" class="btn" style="background: #27ae60; margin-left: 10px;">📊 Скачать Excel-отчет</a>
                <a href="/" class="btn" style="background: #95a5a6; margin-left: 10px;">← На главную</a>
            </div>
            
            <a href="#" class="back-to-top" id="backToTopBtn" title="Наверх">↑</a>

            <script>
                const backToTopBtn = document.getElementById('backToTopBtn');
                window.addEventListener('scroll', () => {{
                    if (window.scrollY > 300) {{
                        backToTopBtn.classList.add('show');
                    }} else {{
                        backToTopBtn.classList.remove('show');
                    }}
                }});
                backToTopBtn.addEventListener('click', (e) => {{
                    e.preventDefault();
                    window.scrollTo({{ top: 0, behavior: 'smooth' }});
                }});
            </script>
        </div>
        {FOOTER_HTML}
    </body></html>
    """

  response = HTMLResponse(content=html_content)
  if not user:
    response.set_cookie(
        key="guest_audit_count",
        value=str(guest_count + 1),
        max_age=2592000,
        httponly=True,
    )
  return response


@app.get("/download/{filename}")
async def download_pdf(filename: str):
  file_path = os.path.join(PDF_DIR, filename)
  if os.path.exists(file_path):
    return FileResponse(
        file_path, media_type="application/pdf", filename=filename
    )
  return HTMLResponse("Файл не найден", status_code=404)


@app.get("/download_excel/{filename}")
async def download_excel(filename: str):
  file_path = os.path.join(PDF_DIR, filename)
  if os.path.exists(file_path):
    return FileResponse(
        file_path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        filename=filename,
    )
  return HTMLResponse("Файл не найден", status_code=404)
