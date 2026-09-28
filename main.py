import asyncio
import hashlib
import io
import json
import os
import re
import secrets
import sqlite3
import time
from collections import defaultdict
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import List, Optional

import aiohttp
import docx
import pandas as pd
import pypdf
from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, relationship, sessionmaker

load_dotenv()

from version import __version__ as APP_VERSION, get_version_info

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./saas_audit.db")
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key-change-in-production")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

YANDEX_GPT_API_KEY = os.getenv("YANDEX_GPT_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "")
GIGACHAT_API_KEY = os.getenv("GIGACHAT_API_KEY", "")

# Кэш access_token для GigaChat
_GIGACHAT_TOKEN_CACHE = {"token": None, "expires_at": 0}

FREE_CHECKS_LIMIT = 5
PRO_CHECKS_LIMIT = 50  # проверок в месяц для Pro
FREE_COMPONENTS_LIMIT = 10

PROGRESS_TRACKER = {}

# ==========================================
# RATE LIMITING
# ==========================================
RATE_LIMIT_WINDOW = 60          # окно в секундах
RATE_LIMIT_GUEST = 5            # для гостей и Free
RATE_LIMIT_PRO = 30             # для Pro и Admin
RATE_LIMIT_GENERAL = 120        # общий лимит для всех эндпоинтов

# Хранилище: {(ip, endpoint): [timestamp1, timestamp2, ...]}
_RATE_BUCKETS = defaultdict(list)


def _get_client_ip(request: Request) -> str:
    """Извлекает IP клиента с учётом Nginx reverse proxy."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        # X-Forwarded-For: client, proxy1, proxy2
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request, endpoint: str, user=None) -> tuple:
    """
    Проверяет лимит запросов.
    Возвращает (allowed: bool, remaining: int, retry_after: int).
    """
    ip = _get_client_ip(request)
    key = (ip, endpoint)
    now = time.time()

    # Убираем старые timestamps
    bucket = _RATE_BUCKETS[key]
    _RATE_BUCKETS[key] = [t for t in bucket if now - t < RATE_LIMIT_WINDOW]
    bucket = _RATE_BUCKETS[key]

    # Определяем лимит по роли
    if user and (user.role == "admin" or user.subscription_plan in ["Pro", "Unlimited"]):
        limit = RATE_LIMIT_PRO
    elif endpoint == "/upload":
        limit = RATE_LIMIT_GUEST
    else:
        limit = RATE_LIMIT_GENERAL

    if len(bucket) >= limit:
        retry_after = int(RATE_LIMIT_WINDOW - (now - bucket[0])) + 1
        return False, 0, retry_after

    bucket.append(now)
    return True, limit - len(bucket), 0


# ==========================================
# RATE LIMITING
# ==========================================
          

def _get_client_ip(request: Request) -> str:
    """Извлекает IP клиента с учётом Nginx reverse proxy."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        # X-Forwarded-For: client, proxy1, proxy2
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"




app = FastAPI(title="Платформа «Компонент-Эксперт» - ПП РФ № 1236", version=APP_VERSION)


# ==========================================
# БАЗА ЗНАНИЙ
# ==========================================
DEFAULT_RULES = {
    "visual studio code": {"license": "MIT", "status": "Разрешено", "recommendation": "IDE не входит в состав ПО."},
    "vscode": {"license": "MIT", "status": "Разрешено", "recommendation": "IDE."},
    "vscodium": {"license": "MIT", "status": "Разрешено", "recommendation": "Open Source IDE."},
    "intellij idea": {"license": "Apache-2.0 / Proprietary", "status": "Разрешено", "recommendation": "IDE."},
    "pycharm": {"license": "Apache-2.0 / Proprietary", "status": "Разрешено", "recommendation": "IDE."},
    "webstorm": {"license": "Commercial / JetBrains", "status": "Разрешено", "recommendation": "IDE."},
    "eclipse": {"license": "EPL-2.0", "status": "Разрешено", "recommendation": "IDE."},
    "netbeans": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "IDE."},

    "cuda": {"license": "NVIDIA EULA", "status": "❌ Запрещено", "recommendation": "Платформа NVIDIA CUDA (привязка к оборудованию вендора)."},
    "nvidia": {"license": "NVIDIA Proprietary", "status": "❌ Запрещено", "recommendation": "Проприетарные компоненты NVIDIA."},

    "ubuntu": {"license": "GPL / Canonical", "status": "Разрешено с условиями", "recommendation": "Условно. Требуется совместимость минимум с 2 российскими ОС."},
    "debian": {"license": "GPL / Debian", "status": "Разрешено", "recommendation": "ОС с открытой лицензией."},
    "windows": {"license": "Commercial EULA", "status": "❌ Запрещено", "recommendation": "Санкционные риски. Требуется совместимость с российскими ОС."},
    "microsoft windows": {"license": "Commercial EULA", "status": "❌ Запрещено", "recommendation": "Иностранная проприетарная ОС."},
    "centos": {"license": "GPL-2.0 / EOL", "status": "❌ Запрещено", "recommendation": "Экспортные ограничения. Используйте ОС из Реестра РФ."},
    "fedora": {"license": "GPL", "status": "❌ Запрещено", "recommendation": "Экспортные ограничения."},
    "opensuse": {"license": "GPL", "status": "❌ Запрещено", "recommendation": "Экспортные ограничения."},
    "red hat enterprise linux": {"license": "Commercial / Subscription", "status": "❌ Запрещено", "recommendation": "Иностранный дистрибутив RHEL."},
    "rhel": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Иностранный дистрибутив."},
    "suse linux enterprise": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Иностранный дистрибутив SUSE."},
    "almalinux": {"license": "GPL", "status": "❌ Запрещено", "recommendation": "Иностранный дистрибутив."},
    "rocky linux": {"license": "GPL", "status": "❌ Запрещено", "recommendation": "Иностранный дистрибутив."},
    "macos": {"license": "Apple EULA", "status": "❌ Запрещено", "recommendation": "Проприетарная иностранная ОС."},
    "alpine": {"license": "MIT / GPL", "status": "⚠️ Требует внимания", "recommendation": "Базовый образ Alpine Linux."},
    "mandriva linux": {"license": "GPL", "status": "Разрешено", "recommendation": "ОС с открытой лицензией."},
    "gentoo linux": {"license": "GPL", "status": "Разрешено", "recommendation": "ОС с открытой лицензией."},
    "freebsd": {"license": "BSD", "status": "Разрешено", "recommendation": "ОС с открытой лицензией."},
    "mint": {"license": "GPL", "status": "Разрешено", "recommendation": "ОС с открытой лицензией."},
    "openbsd": {"license": "BSD", "status": "Разрешено", "recommendation": "ОС с открытой лицензией."},
    "slackware": {"license": "GPL", "status": "Разрешено", "recommendation": "ОС с открытой лицензией."},

    "unity": {
        "license": "Commercial / Proprietary",
        "status": "⚠️ Требует внимания",
        "recommendation": "Временная мера (Письмо Минцифры от 21.08.2023 № АЗ-П11-4-200-216747). Требуется подтвердить: отсутствие выплат правообладателю, отсутствие обязательной регистрации пользователей и отсутствие российских аналогов."
    },
    "unreal": {
        "license": "Commercial EULA",
        "status": "⚠️ Требует внимания",
        "recommendation": "Временная мера (Письмо Минцифры от 21.08.2023 № АЗ-П11-4-200-216747). Требуется подтвердить: отсутствие выплат правообладателю, отсутствие обязательной регистрации пользователей и отсутствие российских аналогов."
    },
    "unreal engine": {
        "license": "Commercial EULA",
        "status": "⚠️ Требует внимания",
        "recommendation": "Временная мера (Письмо Минцифры от 21.08.2023 № АЗ-П11-4-200-216747). Требуется подтвердить: отсутствие выплат правообладателю, отсутствие обязательной регистрации пользователей и отсутствие российских аналогов."
    },

    "astra linux": {"license": "Commercial / FSTEC", "status": "✅ Разрешено (Российское ПО)", "recommendation": "Astra Linux (реестр №369)."},
    "astra linux special edition": {"license": "Commercial / FSTEC", "status": "✅ Разрешено (Российское ПО)", "recommendation": "Astra Linux (реестр №369)."},
    "alt linux": {"license": "GPL / Certificate", "status": "✅ Разрешено (Российское ПО)", "recommendation": "ALT Linux (реестр №1541)."},
    "alt linux 10": {"license": "GPL", "status": "✅ Разрешено (Российское ПО)", "recommendation": "ALT Linux (реестр №1541)."},
    "ред ос": {"license": "Commercial / FSTEC", "status": "✅ Разрешено (Российское ПО)", "recommendation": "РЕД ОС (реестр №3751)."},
    "red os": {"license": "Commercial / FSTEC", "status": "✅ Разрешено (Российское ПО)", "recommendation": "РЕД ОС (реестр №3751)."},
    "роса": {"license": "Commercial / FSTEC", "status": "✅ Разрешено (Российское ПО)", "recommendation": "РОСА (реестр №1610)."},
    "rosa": {"license": "Commercial / FSTEC", "status": "✅ Разрешено (Российское ПО)", "recommendation": "РОСА (реестр №1610)."},
    "postgres pro": {"license": "Commercial", "status": "✅ Разрешено (Российское ПО)", "recommendation": "Postgres Pro (реестр №104)."},
    "postgrespro": {"license": "Commercial", "status": "✅ Разрешено (Российское ПО)", "recommendation": "Postgres Pro (реестр №104)."},
    "криптопро": {"license": "Commercial", "status": "✅ Разрешено (Российское ПО)", "recommendation": "КриптоПро CSP (реестр №2855)."},
    "cryptopro": {"license": "Commercial", "status": "✅ Разрешено (Российское ПО)", "recommendation": "КриптоПро CSP (реестр №2855)."},
    "ред база данных": {"license": "Commercial", "status": "✅ Разрешено (Российское ПО)", "recommendation": "Ред База Данных (реестр №3383)."},
    "liberica": {"license": "Commercial / BellSoft", "status": "✅ Разрешено (Российское ПО)", "recommendation": "Liberica JDK (реестр №5493)."},
    "liberica jdk": {"license": "Commercial / BellSoft", "status": "✅ Разрешено (Российское ПО)", "recommendation": "Liberica JDK (реестр №5493)."},
    "axiom": {"license": "Commercial / ФСТЭК", "status": "✅ Разрешено (Российское ПО)", "recommendation": "Axiom JDK (реестр №17783)."},
    "axiom jdk": {"license": "Commercial / ФСТЭК", "status": "✅ Разрешено (Российское ПО)", "recommendation": "Axiom JDK (реестр №17783)."},
    "динамика jdk": {"license": "Commercial / Для КИИ", "status": "✅ Разрешено (Российское ПО)", "recommendation": "Динамика JDK (реестр №31332)."},
    "dynamika jdk": {"license": "Commercial / Для КИИ", "status": "✅ Разрешено (Российское ПО)", "recommendation": "Динамика JDK (реестр №31332)."},

    "openjdk": {"license": "GPL-2.0 with CE", "status": "⚠️ Требует внимания", "recommendation": "Требуется Liberica JDK (№5493), Axiom JDK (№17783) или Динамика JDK (№31332)."},
    "oracle jdk": {"license": "Commercial / OTN", "status": "❌ Запрещено", "recommendation": "Проприетарная Java. Замена: Liberica JDK или Axiom JDK."},
    "eclipse temurin jdk": {"license": "GPL-2.0 with CE", "status": "⚠️ Требует внимания", "recommendation": "Зарубежная сборка. Замена на Liberica JDK."},
    "temurin": {"license": "GPL-2.0 with CE", "status": "⚠️ Требует внимания", "recommendation": "Замена на Liberica JDK."},
    "corretto": {"license": "Apache-2.0", "status": "⚠️ Требует внимания", "recommendation": "Не входит в Реестр РФ."},
    "zulu": {"license": "GPL-2.0 with CE", "status": "⚠️ Требует внимания", "recommendation": "Не входит в Реестр РФ."},

    "elasticsearch": {"license": "SSPL / Elastic License", "status": "❌ Запрещено", "recommendation": "Санкционные риски. Замена: OpenSearch."},
    "kibana": {"license": "SSPL / Elastic License", "status": "❌ Запрещено", "recommendation": "Замена: OpenSearch Dashboards."},
    "logstash": {"license": "SSPL / Elastic License", "status": "❌ Запрещено", "recommendation": "Санкционные риски."},
    "opensearch": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "OpenSearch."},

    "firebase-admin": {"license": "Apache-2.0 (SDK)", "status": "❌ Запрещено", "recommendation": "Firebase — облако Google. Замена: RuStore Push SDK."},
    "firebase_admin": {"license": "Apache-2.0 (SDK)", "status": "❌ Запрещено", "recommendation": "Firebase Admin SDK."},
    "firebase": {"license": "Proprietary Service", "status": "❌ Запрещено", "recommendation": "Firebase — платформа Google."},
    "google-cloud-firestore": {"license": "Apache-2.0 (SDK)", "status": "❌ Запрещено", "recommendation": "Firestore. Замена: PostgreSQL."},
    "google-cloud-storage": {"license": "Apache-2.0 (SDK)", "status": "❌ Запрещено", "recommendation": "Замена: MinIO."},
    "google-cloud-core": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "Ядро Google Cloud SDK."},
    "google-cloud": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "Google Cloud."},
    "google-api-core": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "GCP."},
    "google-api-python-client": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "Клиент Google API."},
    "google-auth": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "Аутентификация Google."},
    "google-auth-httplib2": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "Google Auth."},
    "google-crc32c": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "GCP."},
    "google-resumable-media": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "GCP."},
    "googleapis-common-protos": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "GCP."},
    "google": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "Google Cloud Platform."},

    "boto3": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "AWS SDK. Замена: MinIO SDK."},
    "botocore": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "Ядро AWS SDK."},
    "s3transfer": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "AWS S3."},
    "aws": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "Amazon Web Services."},
    "aws-sdk": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "AWS SDK."},

    "python-jose": {"license": "MIT", "status": "⚠️ Требует внимания", "recommendation": "CVE-2024-33663, CVE-2024-33664. Замена: PyJWT."},
    "passlib": {"license": "BSD", "status": "⚠️ Требует внимания", "recommendation": "Устаревший. Замена: bcrypt напрямую."},

    "microsoft sql server": {"license": "Commercial EULA", "status": "❌ Запрещено", "recommendation": "Замена на российские СУБД."},
    "oracle database": {"license": "Commercial EULA", "status": "❌ Запрещено", "recommendation": "Замена на PostgresPro."},
    "oracle": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Oracle. Замена на российские решения."},
    "redis enterprise": {"license": "Commercial / SSPL", "status": "❌ Запрещено", "recommendation": "Коммерческая редакция Redis."},
    "sap hana": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "SAP HANA."},
    "sap": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "SAP."},
    "adobe coldfusion": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Adobe."},
    "ibm websphere": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "IBM WebSphere."},
    "amazon web services": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "AWS."},
    "microsoft azure": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Azure."},
    "azure": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Microsoft Azure."},
    "microsoft dynamics": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Microsoft Dynamics."},
    "microsoft sharepoint": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "SharePoint."},
    "sharepoint": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "SharePoint."},
    "microsoft": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Компоненты Microsoft."},

    "spring-core": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "Spring Framework."},
    "spring": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "Spring."},
    "spring-web": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "Spring Web."},
    "spring-security": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "Spring Security."},
    "spring-boot": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "Spring Boot."},
    "junit-jupiter": {"license": "EPL-2.0", "status": "Разрешено", "recommendation": "JUnit."},
    "junit": {"license": "EPL-2.0", "status": "Разрешено", "recommendation": "JUnit."},
    "javax.servlet-api": {"license": "CDDL / GPL-2.0", "status": "Разрешено с условиями", "recommendation": "Проверить линковку."},
    "ojdbc8": {"license": "Commercial EULA", "status": "⚠️ Требует внимания", "recommendation": "Драйвер Oracle DB."},
    "ojdbc": {"license": "Commercial EULA", "status": "⚠️ Требует внимания", "recommendation": "Драйвер Oracle DB."},
    "orai18n": {"license": "Commercial EULA", "status": "⚠️ Требует внимания", "recommendation": "Oracle."},
    "commons-fileupload": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "Apache Commons."},
    "jackson-databind": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "Jackson."},
    "jackson": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "Jackson."},
    "19c": {"license": "Commercial EULA", "status": "⚠️ Требует внимания", "recommendation": "Oracle 19c."},
    "tantor": {"license": "Commercial", "status": "✅ Разрешено (Российское ПО)", "recommendation": "Tantor (реестр РФ)."},
    "nginx-plus-r26": {"license": "Commercial EULA", "status": "⚠️ Требует внимания", "recommendation": "Коммерческий NGINX Plus."},

    "traefik": {"license": "MIT", "status": "Разрешено", "recommendation": "Обратный прокси."},
    "prometheus": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "Мониторинг."},
    "alertmanager": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "Менеджер алертов."},
    "grafana": {"license": "AGPL-3.0", "status": "⚠️ Требует внимания", "recommendation": "AGPL-3.0. Требует изоляции."},
    "influxdb": {"license": "MIT", "status": "Разрешено", "recommendation": "Time-series БД."},
    "golang": {"license": "BSD-3-Clause", "status": "Разрешено", "recommendation": "Go."},
    "rust": {"license": "MIT / Apache-2.0", "status": "Разрешено", "recommendation": "Rust."},
    "cargo": {"license": "MIT / Apache-2.0", "status": "Разрешено", "recommendation": "Cargo."},
    "gradle": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "Gradle."},
    "maven": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "Maven."},
    "npm": {"license": "Artistic-2.0", "status": "Разрешено", "recommendation": "npm."},
    "yarn": {"license": "BSD-2-Clause", "status": "Разрешено", "recommendation": "Yarn."},
    "pip": {"license": "MIT", "status": "Разрешено", "recommendation": "pip."},
    "poetry": {"license": "MIT", "status": "Разрешено", "recommendation": "Poetry."},
    "pnpm": {"license": "MIT", "status": "Разрешено", "recommendation": "pnpm."},

    "hashicorp vault": {"license": "BUSL-1.1", "status": "⚠️ Требует внимания", "recommendation": "BUSL."},
    "vault": {"license": "BUSL-1.1", "status": "⚠️ Требует внимания", "recommendation": "Hashicorp Vault."},
    "mongodb": {"license": "SSPL", "status": "⚠️ Требует внимания", "recommendation": "SSPL. Замена: PostgresPro."},
    "grafana loki": {"license": "AGPL-3.0", "status": "⚠️ Требует внимания", "recommendation": "AGPL."},
    "promtail": {"license": "AGPL-3.0", "status": "⚠️ Требует внимания", "recommendation": "AGPL."},
    "sentry": {"license": "MIT / BSL", "status": "⚠️ Требует внимания", "recommendation": "Sentry."},
    "uwsgi": {"license": "GPL-2.0", "status": "⚠️ Требует внимания", "recommendation": "GPLv2."},

    "mysql": {"license": "GPL-2.0", "status": "Разрешено с условиями", "recommendation": "MySQL."},
    "mariadb": {"license": "GPL-2.0", "status": "Разрешено с условиями", "recommendation": "MariaDB."},
    "redis": {"license": "RSALv2 / SSPL / BSD (до 7.2)", "status": "⚠️ Требует внимания", "recommendation": "С 7.4 — SSPL/RSALv2. Альтернатива: Valkey."},
    "valkey": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "Valkey — форк Redis."},
    "clickhouse": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "ClickHouse."},
    "rabbitmq": {"license": "MPL-2.0", "status": "Разрешено с условиями", "recommendation": "RabbitMQ."},
    "kafka": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "Kafka."},
    "zookeeper": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "ZooKeeper."},
    "sqlite": {"license": "Public Domain", "status": "Разрешено", "recommendation": "SQLite."},

    "systemd": {"license": "LGPL-2.1+", "status": "✅ Разрешено", "recommendation": "Системный менеджер."},
    "bash": {"license": "GPL-3.0", "status": "✅ Разрешено", "recommendation": "Оболочка."},
    "gnu bash": {"license": "GPL-3.0", "status": "✅ Разрешено", "recommendation": "Оболочка."},
    "glibc": {"license": "LGPL-2.1+", "status": "✅ Разрешено", "recommendation": "Системная библиотека C."},
    "gnu c library": {"license": "LGPL-2.1+", "status": "✅ Разрешено", "recommendation": "Системная библиотека C."},
    "busybox": {"license": "GPL-2.0", "status": "✅ Разрешено", "recommendation": "Набор утилит."},
    "containerd": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Контейнерный рантайм."},
    "podman": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Контейнерный движок."},
    "kubernetes": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Оркестрация контейнеров."},
    "helm": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Менеджер пакетов Kubernetes."},
    "kustomize": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Инструмент конфигурации."},
    "etcd": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Хранилище ключ-значение."},

    "npgsql": {"license": "PostgreSQL License", "status": "✅ Разрешено", "recommendation": "Драйвер PostgreSQL для .NET."},
    "pomelo": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Pomelo.EntityFrameworkCore (MySQL)."},
    "pomelo.jsonobject": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Pomelo.JsonObject."},
    "pomelo.entityframeworkcore": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Pomelo EF Core."},
    "devart": {"license": "Commercial", "status": "⚠️ Требует внимания", "recommendation": "Коммерческий драйвер Devart. Требуется лицензия."},
    "enterprisedb": {"license": "Commercial", "status": "⚠️ Требует внимания", "recommendation": "Коммерческая редакция PostgreSQL. Возможна замена на Postgres Pro."},
    "newtonsoft.json": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Newtonsoft.Json."},
    "serilog": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Serilog."},
    "automapper": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "AutoMapper."},
    "swashbuckle": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Swashbuckle для .NET."},
    "swashbuckle.aspnetcore": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Swashbuckle для ASP.NET Core."},
    "entityframework": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Entity Framework Core."},

    "python": {"license": "PSF", "status": "Разрешено", "recommendation": "Python."},
    "black": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Форматтер кода Black."},
    "flake8": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Линтер Flake8."},
    "mypy": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Статический анализатор типов."},
    "isort": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Сортировщик импортов."},
    "pylint": {"license": "GPL-2.0", "status": "✅ Разрешено", "recommendation": "Линтер Pylint."},
    "coverage": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Покрытие тестами."},
    "tox": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Тестовый раннер."},
    "pipenv": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Менеджер зависимостей."},

    "nginx": {"license": "BSD-2-Clause", "status": "Разрешено", "recommendation": "NGINX."},
    "tomcat": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "Tomcat."},
    "haproxy": {"license": "GPL-2.0", "status": "Разрешено с условиями", "recommendation": "HAProxy."},
    "gunicorn": {"license": "MIT", "status": "Разрешено", "recommendation": "Gunicorn."},
    "uvicorn": {"license": "BSD-3-Clause", "status": "Разрешено", "recommendation": "Uvicorn."},
    "fastapi": {"license": "MIT", "status": "Разрешено", "recommendation": "FastAPI."},
    "starlette": {"license": "BSD-3-Clause", "status": "Разрешено", "recommendation": "Starlette."},
    "pydantic": {"license": "MIT", "status": "Разрешено", "recommendation": "Pydantic."},
    "sqlalchemy": {"license": "MIT", "status": "Разрешено", "recommendation": "SQLAlchemy."},
    "alembic": {"license": "MIT", "status": "Разрешено", "recommendation": "Alembic."},
    "docker": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "Docker."},
    "openssl": {"license": "OpenSSL / SSLeay", "status": "Разрешено", "recommendation": "OpenSSL."},
    "requests": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "Requests."},
    "pandas": {"license": "BSD-3-Clause", "status": "Разрешено", "recommendation": "Pandas."},
    "numpy": {"license": "BSD-3-Clause", "status": "Разрешено", "recommendation": "NumPy."},
    "aiohttp": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "aiohttp."},
    "click": {"license": "BSD-3-Clause", "status": "Разрешено", "recommendation": "Click."},
    "jinja2": {"license": "BSD-3-Clause", "status": "Разрешено", "recommendation": "Jinja2."},
    "pyyaml": {"license": "MIT", "status": "Разрешено", "recommendation": "PyYAML."},
    "rich": {"license": "MIT", "status": "Разрешено", "recommendation": "Rich."},
    "openpyxl": {"license": "MIT", "status": "Разрешено", "recommendation": "openpyxl."},
    "reportlab": {"license": "BSD-3-Clause", "status": "Разрешено", "recommendation": "ReportLab."},
    "pypdf": {"license": "BSD-3-Clause", "status": "Разрешено", "recommendation": "pypdf."},
    "python-docx": {"license": "MIT", "status": "Разрешено", "recommendation": "python-docx."},
    "bcrypt": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "bcrypt."},
    "cryptography": {"license": "Apache-2.0 / BSD", "status": "Разрешено", "recommendation": "cryptography."},
    "pyjwt": {"license": "MIT", "status": "Разрешено", "recommendation": "PyJWT."},
    "python-multipart": {"license": "Apache-2.0", "status": "Разрешено", "recommendation": "python-multipart."},
    "python-dotenv": {"license": "BSD-3-Clause", "status": "Разрешено", "recommendation": "python-dotenv."},
    "psycopg2-binary": {"license": "LGPL-3.0", "status": "Разрешено с условиями", "recommendation": "Динамическая линковка."},
    "psycopg2": {"license": "LGPL-3.0", "status": "Разрешено с условиями", "recommendation": "Динамическая линковка."},
    "greenlet": {"license": "MIT", "status": "Разрешено", "recommendation": "greenlet."},
    "httpx": {"license": "BSD-3-Clause", "status": "Разрешено", "recommendation": "httpx."},
    "pytest": {"license": "MIT", "status": "Разрешено", "recommendation": "pytest."},

    # ===== JS / npm экосистема =====
    "vue": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Vue.js — MIT."},
    "vue-router": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Vue Router."},
    "vuex": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Vuex state management."},
    "vue-tsc": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Vue TypeScript compiler."},
    "vite": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Vite bundler."},
    "vitejs": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Vite."},
    "element-plus": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Element Plus UI."},
    "react": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "React."},
    "react-dom": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "React DOM."},
    "angular": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Angular."},
    "babel": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Babel transpiler."},
    "webpack": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Webpack bundler."},
    "papaparse": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "PapaParse CSV parser."},
    "luxon": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Luxon date/time."},
    "uuid": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "UUID generator."},
    "node": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Node.js runtime."},
    "nodejs": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Node.js."},
    "axios": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Axios HTTP client."},
    "lodash": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Lodash utilities."},
    "jquery": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "jQuery."},
    "moment": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Moment.js."},
    "dayjs": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Day.js."},
    "chart.js": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Chart.js."},
    "echarts": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache ECharts."},
    "sass": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Sass compiler."},
    "less": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Less."},
    "typescript": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "TypeScript."},
    "eslint": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "ESLint."},
    "prettier": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Prettier."},
    "next": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Next.js."},
    "nuxt": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Nuxt.js."},
    "svelte": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Svelte."},
    "express": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Express.js."},
    "nestjs": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "NestJS."},

    # ===== Java-компоненты из отчёта =====
    "hibernate": {"license": "LGPL-2.1", "status": "Разрешено с условиями", "recommendation": "Hibernate ORM. Динамическая линковка."},
    "liquibase": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Liquibase DB migrations."},
    "opencsv": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "OpenCSV."},
    "mockserver": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "MockServer."},
    "android-json": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Android JSON."},
    "keycloak": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Keycloak IAM."},
    "postgresql": {"license": "PostgreSQL License", "status": "✅ Разрешено", "recommendation": "PostgreSQL JDBC driver."},
    "awssdk": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "AWS SDK. Замена: MinIO SDK."},
    "aws-sdk-php": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "AWS SDK for PHP. Замена: MinIO SDK."},

    # ============ Инструменты разработки (DevTools) ============
    "git": {"license": "GPL-2.0", "status": "✅ Разрешено", "recommendation": "Git — распределённая СКВ."},
    "gitlab": {"license": "MIT (CE) / Proprietary (EE)", "status": "✅ Разрешено", "recommendation": "GitLab Community Edition — MIT."},
    "gitlab community": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "GitLab CE."},
    "gitea": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Gitea — открытый Git-сервер."},
    "jenkins": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Jenkins — CI/CD."},
    "teamcity": {"license": "Commercial (JetBrains)", "status": "⚠️ Требует внимания", "recommendation": "TeamCity — коммерческий CI."},
    "drone": {"license": "Apache-2.0 (Community)", "status": "✅ Разрешено", "recommendation": "Drone CI."},
    "argocd": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Argo CD — GitOps."},
    "sonarqube": {"license": "LGPL-3.0 (Community)", "status": "✅ Разрешено", "recommendation": "SonarQube Community."},
    "nexus": {"license": "EPL-1.0 / Commercial", "status": "✅ Разрешено", "recommendation": "Nexus Repository OSS."},
    "artifactory": {"license": "Commercial (JFrog)", "status": "⚠️ Требует внимания", "recommendation": "JFrog Artifactory."},
    "jfrog": {"license": "Commercial", "status": "⚠️ Требует внимания", "recommendation": "JFrog."},

    # ============ Веб-серверы ============
    "apache http server": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache HTTP Server."},
    "apache httpd": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache HTTP Server."},
    "httpd": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache HTTP Server."},
    "caddy": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Caddy — веб-сервер на Go."},
    "lighttpd": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "lighttpd."},
    "openresty": {"license": "BSD-2-Clause", "status": "✅ Разрешено", "recommendation": "OpenResty."},

    # ============ Языки и рантаймы ============
    "go": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "Go (Golang)."},
    "php": {"license": "PHP License 3.01", "status": "✅ Разрешено", "recommendation": "PHP."},
    "ruby": {"license": "Ruby License / BSD-2-Clause", "status": "✅ Разрешено", "recommendation": "Ruby."},
    "perl": {"license": "Artistic-2.0 / GPL-1.0", "status": "✅ Разрешено", "recommendation": "Perl."},
    "dotnet": {"license": "MIT", "status": "✅ Разрешено", "recommendation": ".NET — MIT."},
    ".net": {"license": "MIT", "status": "✅ Разрешено", "recommendation": ".NET."},
    ".net sdk": {"license": "MIT", "status": "✅ Разрешено", "recommendation": ".NET SDK."},
    "dotnet sdk": {"license": "MIT", "status": "✅ Разрешено", "recommendation": ".NET SDK."},
    "elastic beats": {"license": "Elastic License 2.0", "status": "❌ Запрещено", "recommendation": "Elastic Beats — Elastic License. Замена: Fluent Bit."},
    "filebeat": {"license": "Elastic License 2.0", "status": "❌ Запрещено", "recommendation": "Filebeat (Elastic) — Замена: Fluent Bit."},
    "metricbeat": {"license": "Elastic License 2.0", "status": "❌ Запрещено", "recommendation": "Metricbeat (Elastic) — Замена: Prometheus."},
    "packetbeat": {"license": "Elastic License 2.0", "status": "❌ Запрещено", "recommendation": "Packetbeat (Elastic)."},
    "heartbeat": {"license": "Elastic License 2.0", "status": "❌ Запрещено", "recommendation": "Heartbeat (Elastic)."},
    "auditbeat": {"license": "Elastic License 2.0", "status": "❌ Запрещено", "recommendation": "Auditbeat (Elastic)."},
    "fluent bit": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Fluent Bit."},
    "fluentbit": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Fluent Bit."},
    "fluent-bit": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Fluent Bit."},
    "fluentd": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Fluentd."},
    "jaeger": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Jaeger — трассировка."},
    "zipkin": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Zipkin."},
    "tempo": {"license": "AGPL-3.0", "status": "⚠️ Требует внимания", "recommendation": "Grafana Tempo — AGPL."},
    "erlang": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Erlang/OTP."},
    "elixir": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Elixir."},
    "kotlin": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Kotlin."},
    "scala": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Scala."},
    "dart": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "Dart."},
    "lua": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Lua."},

    # ============ Компиляторы и сборка ============
    "gcc": {"license": "GPL-3.0 with GCC exception", "status": "✅ Разрешено", "recommendation": "GCC."},
    "g++": {"license": "GPL-3.0 with GCC exception", "status": "✅ Разрешено", "recommendation": "G++."},
    "clang": {"license": "Apache-2.0 with LLVM exception", "status": "✅ Разрешено", "recommendation": "Clang/LLVM."},
    "llvm": {"license": "Apache-2.0 with LLVM exception", "status": "✅ Разрешено", "recommendation": "LLVM."},
    "cmake": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "CMake."},
    "make": {"license": "GPL-3.0", "status": "✅ Разрешено", "recommendation": "GNU Make."},
    "gnu make": {"license": "GPL-3.0", "status": "✅ Разрешено", "recommendation": "GNU Make."},
    "ninja": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Ninja build."},
    "bazel": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Bazel."},
    "msbuild": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "MSBuild."},

    # ============ IDE и редакторы ============
    "visual studio community": {"license": "Free (Microsoft EULA)", "status": "⚠️ Требует внимания", "recommendation": "Visual Studio Community — EULA Microsoft."},
    "visual studio": {"license": "Commercial (Microsoft)", "status": "⚠️ Требует внимания", "recommendation": "Visual Studio — Microsoft."},
    "vim": {"license": "Vim License", "status": "✅ Разрешено", "recommendation": "Vim."},
    "neovim": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Neovim."},
    "emacs": {"license": "GPL-3.0", "status": "✅ Разрешено", "recommendation": "GNU Emacs."},
    "sublime text": {"license": "Commercial", "status": "⚠️ Требует внимания", "recommendation": "Sublime Text."},

    # ============ AI / ML фреймворки ============
    "pytorch": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "PyTorch."},
    "torch": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "PyTorch."},
    "jax": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "JAX."},
    "onnx": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "ONNX."},
    "onnxruntime": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "ONNX Runtime."},
    "cudnn": {"license": "NVIDIA Proprietary EULA", "status": "❌ Запрещено", "recommendation": "cuDNN — проприетарный NVIDIA. Замена: OpenVINO / oneDNN."},
    "tensorrt": {"license": "NVIDIA Proprietary EULA", "status": "❌ Запрещено", "recommendation": "TensorRT — NVIDIA. Замена: OpenVINO."},
    "nccl": {"license": "NVIDIA / BSD-3-Clause", "status": "⚠️ Требует внимания", "recommendation": "NCCL — NVIDIA."},
    "opencv": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "OpenCV."},
    "scikit-learn": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "scikit-learn."},
    "scipy": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "SciPy."},
    "matplotlib": {"license": "BSD (PSF-based)", "status": "✅ Разрешено", "recommendation": "Matplotlib."},
    "huggingface": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Hugging Face."},
    "transformers": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Hugging Face Transformers."},
    "langchain": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "LangChain."},
    "openvino": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "OpenVINO — Intel."},

    # ============ БД и хранилища ============
    "oracle nosql": {"license": "Commercial", "status": "❌ Запрещено", "recommendation": "Oracle NoSQL. Замена: Postgres Pro."},
    "neo4j": {"license": "GPL-3.0 (Community) / Commercial (Enterprise)", "status": "✅ Разрешено", "recommendation": "Neo4j Community — GPLv3."},
    "cassandra": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache Cassandra."},
    "scylladb": {"license": "AGPL-3.0", "status": "⚠️ Требует внимания", "recommendation": "ScyllaDB — AGPL-3.0."},

    # ============ Утилиты и OS-инструменты ============
    "curl": {"license": "MIT-like (curl license)", "status": "✅ Разрешено", "recommendation": "curl."},
    "wget": {"license": "GPL-3.0", "status": "✅ Разрешено", "recommendation": "GNU Wget."},
    "rsync": {"license": "GPL-3.0", "status": "✅ Разрешено", "recommendation": "rsync."},
    "openssh": {"license": "BSD-style", "status": "✅ Разрешено", "recommendation": "OpenSSH."},
    "ssh": {"license": "BSD-style (OpenSSH)", "status": "✅ Разрешено", "recommendation": "OpenSSH."},
    "docker compose": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Docker Compose."},
    "ansible": {"license": "GPL-3.0", "status": "✅ Разрешено", "recommendation": "Ansible."},
    "terraform": {"license": "BUSL-1.1", "status": "⚠️ Требует внимания", "recommendation": "Terraform — BUSL."},
    "puppet": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Puppet."},
    "chef": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Chef."},
    "saltstack": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "SaltStack."},
    "vagrant": {"license": "BUSL-1.1", "status": "⚠️ Требует внимания", "recommendation": "Vagrant — BUSL."},
    "packer": {"license": "BUSL-1.1", "status": "⚠️ Требует внимания", "recommendation": "Packer — BUSL."},

    # ============ AI/ML дополнительные ============
    "vllm": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "vLLM — Apache-2.0."},
    "llama.cpp": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "llama.cpp — MIT."},
    "llamacpp": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "llama.cpp — MIT."},
    "ollama": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Ollama — MIT."},
    "jupyter": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "Jupyter — BSD-3-Clause."},
    "jupyterlab": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "JupyterLab — BSD-3-Clause."},
    "jupyter notebook": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "Jupyter Notebook."},
    "tensorflow": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "TensorFlow — Apache-2.0."},
    "mlflow": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "MLflow — Apache-2.0."},
    "dvc": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "DVC — Apache-2.0."},
    "ray": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Ray — Apache-2.0."},
    "dask": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "Dask — BSD."},
    "polars": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Polars — MIT."},
    "lightgbm": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "LightGBM — MIT."},
    "xgboost": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "XGBoost — Apache-2.0."},
    "catboost": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "CatBoost — Apache-2.0."},
    "stable diffusion": {"license": "OpenRAIL-M", "status": "⚠️ Требует внимания", "recommendation": "Stable Diffusion — OpenRAIL-M."},
    "diffusers": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Hugging Face Diffusers."},

    # ============ Python DevTools ============
    "ruff": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Ruff — быстрый линтер, MIT."},
    "uv": {"license": "Apache-2.0 / MIT", "status": "✅ Разрешено", "recommendation": "uv (astral-sh)."},
    "pdm": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "PDM."},
    "hatch": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Hatch."},
    "pipx": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "pipx."},
    "pre-commit": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "pre-commit."},
    "bandit": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Bandit — security linter."},
    "safety": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Safety."},

    # ============ IaC / Policy ============
    "open policy agent": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Open Policy Agent — Apache-2.0."},
    "opa": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Open Policy Agent."},
    "hashicorp boundary": {"license": "BUSL-1.1", "status": "⚠️ Требует внимания", "recommendation": "HashiCorp Boundary — BUSL."},
    "boundary": {"license": "BUSL-1.1", "status": "⚠️ Требует внимания", "recommendation": "HashiCorp Boundary — BUSL."},
    "consul": {"license": "BUSL-1.1", "status": "⚠️ Требует внимания", "recommendation": "HashiCorp Consul — BUSL."},
    "nomad": {"license": "BUSL-1.1", "status": "⚠️ Требует внимания", "recommendation": "HashiCorp Nomad — BUSL."},
    "pulumi": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Pulumi — Apache-2.0."},

    # ============ Maven namespace-правила (Java) ============
    # Spring
    "org.springframework": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Spring Framework."},
    "org.springframework.boot": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Spring Boot."},
    "org.springframework.security": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Spring Security."},
    "org.springframework.cloud": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Spring Cloud."},
    "org.springframework.ai": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Spring AI."},
    "org.springframework.kafka": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Spring Kafka."},
    "org.springframework.retry": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Spring Retry."},

    # Apache
    "org.apache.commons": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache Commons."},
    "org.apache.tika": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache Tika."},
    "org.apache.poi": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache POI."},
    "org.apache.pdfbox": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache PDFBox."},
    "org.apache.httpcomponents": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache HttpComponents."},
    "org.apache.kafka": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache Kafka."},
    "org.apache.logging": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache Logging."},
    "org.apache.opennlp": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache OpenNLP."},
    "org.apache.james": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache James."},
    "org.apache.xmlbeans": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache XMLBeans."},
    "org.apache.tomcat": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apache Tomcat."},
    "org.apache.antlr": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "ANTLR."},
    "org.apache.zookeeper": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "ZooKeeper."},

    # Google
    "com.google.guava": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Google Guava."},
    "com.google.code.gson": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Gson."},
    "com.google.code.findbugs": {"license": "LGPL-3.0", "status": "✅ Разрешено", "recommendation": "FindBugs."},
    "com.google.protobuf": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "Protobuf."},
    "com.google.errorprone": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Error Prone."},
    "com.google.api.grpc": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "gRPC-Google."},
    "com.google.android": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Google Annotations."},
    "com.google.j2objc": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "J2ObjC."},
    "com.googlecode.plist": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "dd-plist."},

    # Jackson
    "com.fasterxml.jackson": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Jackson."},
    "com.fasterxml": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "FasterXML."},

    # Bouncy Castle / Netty / gRPC
    "org.bouncycastle": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Bouncy Castle."},
    "io.netty": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Netty."},
    "io.grpc": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "gRPC."},

    # Observability
    "io.opentelemetry": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "OpenTelemetry."},
    "io.opentelemetry.semconv": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "OTel SemConv."},
    "io.micrometer": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Micrometer."},
    "io.prometheus": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Prometheus Client."},
    "io.perfmark": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "PerfMark."},
    "io.projectreactor": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Project Reactor."},
    "io.qdrant": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Qdrant client."},
    "io.swagger.core.v3": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Swagger Core."},

    # Jakarta
    "jakarta.activation": {"license": "EPL-2.0 / GPL-2.0", "status": "✅ Разрешено", "recommendation": "Jakarta Activation."},
    "jakarta.annotation": {"license": "EPL-2.0 / GPL-2.0", "status": "✅ Разрешено", "recommendation": "Jakarta Annotations."},
    "jakarta.validation": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Jakarta Validation."},
    "jakarta.xml.bind": {"license": "EPL-2.0 / GPL-2.0", "status": "✅ Разрешено", "recommendation": "Jakarta XML Bind."},
    "javax.validation": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "javax.validation."},

    # Test
    "org.junit": {"license": "EPL-2.0", "status": "✅ Разрешено", "recommendation": "JUnit."},
    "org.junit.jupiter": {"license": "EPL-2.0", "status": "✅ Разрешено", "recommendation": "JUnit 5."},
    "org.junit.platform": {"license": "EPL-2.0", "status": "✅ Разрешено", "recommendation": "JUnit Platform."},
    "junit": {"license": "EPL-1.0", "status": "✅ Разрешено", "recommendation": "JUnit 4."},
    "org.mockito": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Mockito."},
    "org.assertj": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "AssertJ."},
    "org.hamcrest": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "Hamcrest."},
    "org.awaitility": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Awaitility."},
    "org.apiguardian": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Apiguardian."},
    "org.opentest4j": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "OpenTest4J."},
    "org.xmlunit": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "XMLUnit."},
    "org.skyscreamer": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "JSONassert."},
    "org.testcontainers": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Testcontainers."},

    # Logging
    "ch.qos.logback": {"license": "EPL-1.0 / LGPL-2.1", "status": "✅ Разрешено", "recommendation": "Logback."},
    "org.slf4j": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "SLF4J."},
    "net.logstash.logback": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Logstash Encoder."},

    # Nimbus / Square
    "com.nimbusds": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Nimbus JOSE+JWT."},
    "com.squareup.okhttp3": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "OkHttp."},
    "com.squareup.okio": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Okio."},

    # Котлин
    "org.jetbrains": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "JetBrains Annotations."},
    "org.jetbrains.kotlin": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Kotlin stdlib."},

    # Прочее
    "com.github.ben-manes.caffeine": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Caffeine cache."},
    "com.github.victools": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "JSON Schema Generator."},
    "com.github.docker-java": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Docker Java client."},
    "com.github.junrar": {"license": "UnRAR License", "status": "⚠️ Требует внимания", "recommendation": "junrar — нестандартная лицензия."},
    "com.github.luben": {"license": "BSD-2-Clause", "status": "✅ Разрешено", "recommendation": "Zstd-JNI."},
    "com.github.stephenc.jcip": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "JCIP Annotations."},
    "com.github.jai-imageio": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "JAI ImageIO."},
    "com.healthmarketscience.jackcess": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Jackcess."},
    "com.ethlo.time": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "ITU library."},
    "com.zaxxer": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "SparseBitSet."},
    "com.rometools": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "ROME."},
    "com.pff": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "java-libpst."},
    "com.jayway.jsonpath": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "JsonPath."},
    "com.knuddels": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "jtokkit."},
    "com.networknt": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "JSON Schema Validator."},
    "com.drewnoakes": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "metadata-extractor."},
    "com.adobe.xmp": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "XMPCore."},
    "com.epam": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Parso."},
    "com.sun.istack": {"license": "EPL-2.0 / GPL-2.0", "status": "✅ Разрешено", "recommendation": "istack-commons."},
    "com.github.albfernandez": {"license": "LGPL-2.1 / MPL-1.1", "status": "✅ Разрешено", "recommendation": "juniversalchardet."},
    "com.vaadin.external.google": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Android JSON for tests."},
    "org.codelibs": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "jhighlight."},
    "org.eclipse.angus": {"license": "EPL-2.0 / GPL-2.0", "status": "✅ Разрешено", "recommendation": "Angus Activation."},
    "org.glassfish.jaxb": {"license": "EPL-2.0 / GPL-2.0", "status": "✅ Разрешено", "recommendation": "Glassfish JAXB."},
    "org.jboss.logging": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "JBoss Logging."},
    "org.hibernate.validator": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Hibernate Validator."},
    "org.gagravarr": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Vorbis-Java."},
    "org.json": {"license": "JSON License (MIT-like)", "status": "✅ Разрешено", "recommendation": "JSON-java."},
    "org.jsoup": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "jsoup."},
    "org.jspecify": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "JSpecify."},
    "org.jdom": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "JDOM2."},
    "org.latencyutils": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "LatencyUtils."},
    "org.objenesis": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Objenesis."},
    "org.ow2.asm": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "ASM."},
    "org.projectlombok": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Lombok."},
    "org.reactivestreams": {"license": "MIT-0", "status": "✅ Разрешено", "recommendation": "Reactive Streams."},
    "org.rnorth.duct-tape": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Duct Tape."},
    "org.hdrhistogram": {"license": "BSD-2-Clause", "status": "✅ Разрешено", "recommendation": "HdrHistogram."},
    "org.netpreserve": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "jwarc."},
    "org.tallison": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "jmatio."},
    "org.tukaani": {"license": "Public Domain", "status": "✅ Разрешено", "recommendation": "XZ for Java."},
    "org.brotli": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "Brotli decoder."},
    "org.yaml": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "SnakeYAML."},
    "org.webjars": {"license": "MIT", "status": "✅ Разрешено", "recommendation": "WebJars."},
    "org.springdoc": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "SpringDoc OpenAPI."},
    "info.picocli": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "picocli."},
    "io.github.openfeign": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "OpenFeign."},
    "net.bytebuddy": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Byte Buddy."},
    "net.java.dev.jna": {"license": "LGPL-2.1 / Apache-2.0", "status": "✅ Разрешено", "recommendation": "JNA."},
    "net.minidev": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "json-smart."},
    "software.amazon.awssdk": {"license": "Apache-2.0", "status": "⚠️ Требует внимания", "recommendation": "AWS SDK. Интеграция опциональна."},
    "dev.langchain4j": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "LangChain4j."},
    "commons-codec": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Commons Codec."},
    "commons-io": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Commons IO."},
    "commons-logging": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Commons Logging."},
    "commons-fileupload": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "Commons FileUpload."},
    "aopalliance": {"license": "Public Domain", "status": "✅ Разрешено", "recommendation": "AOP Alliance."},
    "at.yawk.lz4": {"license": "Apache-2.0", "status": "✅ Разрешено", "recommendation": "lz4-java."},
    "org.antlr": {"license": "BSD-3-Clause", "status": "✅ Разрешено", "recommendation": "ANTLR runtime."},
}


# ==========================================
# ИИ-АГЕНТ
# ==========================================
AI_PROMPT_TEMPLATE = """Ты — эксперт по регуляторике российского ПО (ПП РФ № 1236, реестр Минцифры). Проанализируй компонент '{component}' пошагово.

ШАГ 1. Определи лицензию.
ШАГ 2. Классифицируй риск: НИЗКИЙ / СРЕДНИЙ / ВЫСОКИЙ / ПРОПРИЕТАРНАЯ.
ШАГ 3. Проверь санкционные риски.
ШАГ 4. Специфика: Java → российская сборка; Redis 7.4+/MongoDB → SSPL; Elasticsearch → OpenSearch; Windows/CentOS/RHEL → запрещено.

ВАЖНО: Если ты не знаешь точную лицензию, верни "license": "Unknown", "status": "⚠️ Требует внимания". Не выдумывай названия компонентов. Не вставляй текст этой инструкции в свой ответ.

ШАГ 5. Верни СТРОГО JSON без markdown:
{{"license": "...", "status": "...", "risk_level": "low/medium/high", "recommendation": "...", "registry_analog": "..."}}"""


def _extract_json(content: str) -> Optional[dict]:
    if not content:
        return None
    try:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        print(f"[AI] JSON parse error: {e}")
    return None


async def _call_yandex(session: aiohttp.ClientSession, prompt: str) -> Optional[dict]:
    if not YANDEX_GPT_API_KEY or not YANDEX_FOLDER_ID:
        return None
    try:
        url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
        headers = {"Authorization": f"Api-Key {YANDEX_GPT_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "modelUri": f"gpt://{YANDEX_FOLDER_ID}/yandexgpt/latest",
            "completionOptions": {"stream": False, "temperature": 0.1, "maxTokens": 700},
            "messages": [{"role": "user", "text": prompt}],
        }
        async with session.post(url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status == 200:
                data = await resp.json()
                parsed = _extract_json(data["result"]["alternatives"][0]["message"]["text"])
                if parsed:
                    parsed["provider"] = "YandexGPT"
                    return parsed
    except Exception as e:
        print(f"[AI] Yandex error: {e}")
    return None


async def _get_gigachat_token(session: aiohttp.ClientSession) -> Optional[str]:
    """Обменивает Authorization Key на access_token (OAuth)."""
    now = time.time()
    if _GIGACHAT_TOKEN_CACHE["token"] and now < _GIGACHAT_TOKEN_CACHE["expires_at"] - 60:
        return _GIGACHAT_TOKEN_CACHE["token"]

    if not GIGACHAT_API_KEY:
        return None

    try:
        import uuid
        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        headers = {
            "Authorization": f"Basic {GIGACHAT_API_KEY}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        data = {"scope": "GIGACHAT_API_PERS"}
        async with session.post(url, headers=headers, data=data, ssl=False,
                                timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status == 200:
                result = await resp.json()
                token = result.get("access_token")
                expires = result.get("expires_at", 0) / 1000  # мс → сек
                _GIGACHAT_TOKEN_CACHE["token"] = token
                _GIGACHAT_TOKEN_CACHE["expires_at"] = expires
                print(f"[AI] GigaChat: получен новый токен (до {datetime.fromtimestamp(expires).strftime('%H:%M:%S')})")
                return token
            else:
                err = await resp.text()
                print(f"[AI] GigaChat OAuth ошибка: {resp.status} {err[:200]}")
    except Exception as e:
        print(f"[AI] GigaChat OAuth исключение: {e}")
    return None


async def _call_gigachat(session: aiohttp.ClientSession, prompt: str) -> Optional[dict]:
    if not GIGACHAT_API_KEY:
        return None
    try:
        token = await _get_gigachat_token(session)
        if not token:
            return None
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"model": "GigaChat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
        # Retry при 429 (rate limit) — до 3 попыток
        for attempt in range(3):
            async with session.post(url, headers=headers, json=payload, ssl=False,
                                    timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    parsed = _extract_json(data["choices"][0]["message"]["content"])
                    if parsed:
                        parsed["provider"] = "GigaChat"
                        return parsed
                elif resp.status == 429:
                    wait = 2 + attempt * 2  # 2, 4, 6 сек
                    print(f"[AI] GigaChat 429, ждём {wait}с (попытка {attempt+1}/3)")
                    await asyncio.sleep(wait)
                    continue
                else:
                    err = await resp.text()
                    print(f"[AI] GigaChat chat ошибка: {resp.status} {err[:200]}")
                    return None
    except Exception as e:
        print(f"[AI] GigaChat error: {e}")
    return None


async def _get_ai_cache(component_name: str):
    """Получает запись из кэша ИИ-ответов. Возвращает (license, status, rec, provider) или None."""
    def query():
        db = SessionLocal()
        try:
            key = (component_name or "").lower().strip()
            if not key:
                return None
            now = datetime.utcnow()
            cache = db.query(AILicenseCache).filter(AILicenseCache.component_name == key).first()
            if not cache:
                return None
            # TTL: 1 час для неудачных, 90 дней для успешных
            ttl_seconds = 3600 if cache.is_failure else 90 * 86400
            age_seconds = (now - cache.created_at).total_seconds() if cache.created_at else 0
            if age_seconds > ttl_seconds:
                db.delete(cache)
                db.commit()
                return None
            cache.hit_count = (cache.hit_count or 0) + 1
            cache.last_used = now
            db.commit()
            return (cache.license, cache.status, cache.recommendation or "", cache.provider or "")
        except Exception as e:
            print(f"[AI CACHE] Ошибка чтения: {e}")
            return None
        finally:
            db.close()
    return await asyncio.to_thread(query)


async def _save_ai_cache(component_name, license_, status, recommendation, provider, is_failure=False):
    """Сохраняет ответ ИИ в кэш."""
    def save():
        db = SessionLocal()
        try:
            key = (component_name or "").lower().strip()
            if not key:
                return
            existing = db.query(AILicenseCache).filter(AILicenseCache.component_name == key).first()
            if existing:
                existing.license = license_
                existing.status = status
                existing.recommendation = recommendation
                existing.provider = provider
                existing.is_failure = is_failure
                existing.created_at = datetime.utcnow()
            else:
                db.add(AILicenseCache(
                    component_name=key,
                    license=license_,
                    status=status,
                    recommendation=recommendation,
                    provider=provider,
                    is_failure=is_failure,
                ))
            db.commit()
        except Exception as e:
            print(f"[AI CACHE] Ошибка записи: {e}")
            db.rollback()
        finally:
            db.close()
    await asyncio.to_thread(save)


def cleanup_ai_cache():
    """Удаляет устаревшие записи кэша ИИ."""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        old_success = db.query(AILicenseCache).filter(
            AILicenseCache.is_failure == False,
            AILicenseCache.created_at < now - timedelta(days=90)
        ).delete()
        old_failure = db.query(AILicenseCache).filter(
            AILicenseCache.is_failure == True,
            AILicenseCache.created_at < now - timedelta(hours=1)
        ).delete()
        db.commit()
        if old_success or old_failure:
            print(f"[AI CACHE] Очищено: {old_success} успешных, {old_failure} неудачных")
    except Exception as e:
        print(f"[AI CACHE] Ошибка очистки: {e}")
    finally:
        db.close()


async def ask_ai_for_license(component_name: str, provider: str = "auto") -> tuple:
    # --- Проверка кэша ---
    cached = await _get_ai_cache(component_name)
    if cached:
        lic, st, rec, prov = cached
        print(f"[AI CACHE] ✅ Хит для '{component_name}': {lic}")
        cache_note = f" (из кэша: {prov})" if prov else " (из кэша)"
        return (lic, st, rec + cache_note)

    prompt = AI_PROMPT_TEMPLATE.format(component=component_name)
    if provider == "auto":
        chain = ["yandex", "gigachat"]
    else:
        chain = [provider] + [p for p in ["yandex", "gigachat"] if p != provider]

    async with aiohttp.ClientSession() as session:
        for p in chain:
            result = None
            try:
                if p == "yandex":
                    result = await _call_yandex(session, prompt)
                elif p == "gigachat":
                    result = await _call_gigachat(session, prompt)
            except Exception as e:
                print(f"[AI] Fallback {p} failed: {e}")

            if result and result.get("license"):
                print(f"[AI] ✅ Ответ от {result['provider']} для '{component_name}'")
                rec = result.get("recommendation", "")
                analog = result.get("registry_analog", "")
                if analog:
                    rec += f" Российский аналог: {analog}."
                final_rec = f"{rec} (ИИ: {result['provider']})"
                final_status = result.get("status", "⚠️ Требует внимания")
                await _save_ai_cache(component_name, result["license"], final_status, final_rec, result["provider"], is_failure=False)
                return (result["license"], final_status, final_rec)

    print(f"[AI] ❌ Все ИИ недоступны для '{component_name}'.")
    fail_msg = f"Не удалось определить лицензию для '{component_name}'. Требуется ручная проверка."
    await _save_ai_cache(component_name, "Не определена", "⚠️ Требует внимания", fail_msg, None, is_failure=True)
    return ("Не определена", "⚠️ Требует внимания", fail_msg)


# ==========================================
# ОПРЕДЕЛЕНИЕ КАТЕГОРИЙ
# ==========================================
def _category_badge(cat: str) -> str:
    """Возвращает HTML-бейдж для категории с фиксированным цветом."""
    colors = {
        "Операционные системы": "#e53e3e",
        "СУБД и хранилища": "#dd6b20",
        "Языки и рантаймы": "#3182ce",
        "Фреймворки": "#805ad5",
        "Библиотеки": "#38a169",
        "Мониторинг и логирование": "#319795",
        "Очереди сообщений": "#5a67d8",
        "Контейнеризация и оркестрация": "#00b5d8",
        "Облачные сервисы": "#0ea5e9",
        "Игровые движки": "#ed64a6",
        "ИИ и ML": "#d53f8c",
        "Инструменты разработки": "#718096",
        "IDE и редакторы": "#2c5282",
        "Системные библиотеки": "#4a5568",
        "Прочее": "#a0aec0",
    }
    color = colors.get(cat, "#a0aec0")
    # Короткие метки для длинных категорий
    short = {
        "Мониторинг и логирование": "Мониторинг",
        "Контейнеризация и оркестрация": "Контейнеры",
        "Инструменты разработки": "Инструменты",
        "Операционные системы": "ОС",
        "СУБД и хранилища": "СУБД",
        "Языки и рантаймы": "Языки",
        "Игровые движки": "Геймдев",
        "Очереди сообщений": "Очереди",
        "Облачные сервисы": "Облако",
        "IDE и редакторы": "IDE",
    }
    label = short.get(cat, cat)
    return f'<span style="display:inline-block;background:{color};color:white;padding:4px 10px;border-radius:12px;font-size:11px;font-weight:600;white-space:nowrap;min-width:80px;text-align:center;">{label}</span>'


def _detect_category(name: str) -> str:
    n = (name or "").lower().strip()
    if not n:
        return "Прочее"

    # ВАЖНО: СУБД проверяем РАНЬШЕ игровых движков, чтобы "community" не
    # попадало под "unity". Используем границы слов через regex.
    def _has_word(text, word):
        return re.search(r'\b' + re.escape(word) + r'\b', text) is not None

    # Очереди сообщений и брокеры (ДО СУБД, чтобы Kafka/RabbitMQ попали сюда)
    mq_keys = ["kafka", "rabbitmq", "activemq", "artemis", "nats", "zeromq", "pulsar",
               "rocketmq", "ibm mq", "rabbit", "qpid", "emqx", "mosquitto"]
    if any(_has_word(n, k) for k in mq_keys) or "activemq artemis" in n:
        return "Очереди сообщений"

    # Мониторинг и логирование
    # Elasticsearch/OpenSearch/Kibana/Logstash — это СУБД/поиск, не мониторинг
    monitor_keys = ["zabbix", "prometheus", "grafana", "nagios", "datadog",
                    "new relic", "splunk", "loki", "jaeger", "zipkin", "tempo",
                    "opentelemetry", "otel", "sentry", "victoriametrics",
                    "influxdb", "telegraf", "fluentd", "fluentbit", "fluent-bit",
                    "filebeat", "metricbeat", "vector"]
    if any(_has_word(n, k) for k in monitor_keys):
        return "Мониторинг и логирование"

    # СУБД и хранилища (после очередей и мониторинга)
    db_keys = ["postgres", "mysql", "mariadb", "oracle", "sql server", "sqlite", "mongodb",
               "redis", "valkey", "clickhouse", "cassandra", "scylladb", "couchdb", "neo4j",
               "zookeeper", "sap hana", "enterprisedb", "npgsql", "db2", "teradata",
               "firebird", "hive", "tibero", "tmax",
               "elasticsearch", "opensearch", "kibana", "logstash", "graylog"]
    if any(_has_word(n, k) for k in db_keys):
        return "СУБД и хранилища"

    # Игровые движки (после СУБД)
    if any(_has_word(n, k) for k in ["unity", "unreal", "godot", "cryengine"]):
        return "Игровые движки"

    if any(_has_word(n, k) for k in ["aws", "azure", "firebase", "amazon", "yandex cloud", "sbercloud"]):
        return "Облачные сервисы"

    if any(_has_word(n, k) for k in ["docker", "kubernetes", "containerd", "podman", "helm",
                                      "kustomize", "openshift", "rancher", "istio", "envoy", "etcd", "traefik"]):
        return "Контейнеризация и оркестрация"

    os_keys = ["windows", "linux", "ubuntu", "debian", "centos", "rhel", "fedora",
               "suse", "alpine", "astra", "macos", "freebsd", "openbsd", "gentoo",
               "almalinux", "rocky", "opensuse", "slackware", "mandriva", "mint",
               "busybox", "systemd", "glibc", "bash"]
    if any(_has_word(n, k) for k in os_keys) or "red hat" in n or "alt linux" in n or "ред ос" in n or "red os" in n or "роса" in n:
        return "Операционные системы"

    if any(k in n for k in ["tensorflow", "pytorch", "keras", "scikit",
                            "transformers", "openai", "gigachat", "yandexgpt", "ollama", "langchain"]):
        return "ИИ и ML"

    runtime_keys = ["python", "java", "openjdk", "oracle jdk", "node", "nodejs", "golang",
                    "rust", "cargo", "dotnet", ".net", "ruby", "php", "perl", "jdk",
                    "temurin", "corretto", "zulu"]
    if any(k in n for k in runtime_keys):
        return "Языки и рантаймы"

    fw_keys = ["fastapi", "django", "flask", "spring", "starlette", "react", "vue", "angular",
               "next.js", "nuxt", "svelte", "express", "nestjs", "laravel", "rails"]
    if any(k in n for k in fw_keys):
        return "Фреймворки"

    if any(k in n for k in ["intellij", "pycharm", "webstorm", "vscode", "visual studio",
                            "eclipse", "netbeans", "vscodium"]):
        return "IDE и редакторы"

    tools_keys = ["git", "maven", "gradle", "npm", "yarn", "pnpm", "pip", "poetry",
                  "webpack", "babel", "eslint", "prettier", "black", "flake8", "pytest",
                  "junit", "mocha", "jest", "vite", "rollup", "mypy", "isort", "pylint",
                  "coverage", "tox", "pipenv"]
    if any(k in n for k in tools_keys):
        return "Инструменты разработки"

    lib_keys = ["requests", "httpx", "aiohttp", "sqlalchemy", "pydantic", "jinja2",
                "openpyxl", "reportlab", "python-docx", "pypdf", "bcrypt", "cryptography",
                "pyjwt", "python-multipart", "python-dotenv", "pandas", "greenlet",
                "alembic", "psycopg2", "pymongo", "newtonsoft", "serilog", "automapper",
                "swashbuckle", "entityframework", "pomelo", "jackson", "commons-fileupload"]
    if any(k in n for k in lib_keys):
        return "Библиотеки"

    if n.startswith("lib"):
        return "Системные библиотеки"

    return "Прочее"


# ==========================================
# ПРОВЕРКА УЯЗВИМОСТЕЙ (OSV API)
# ==========================================
def _detect_ecosystem(package_name: str) -> Optional[str]:
    """Определяет экосистему пакета для OSV API."""
    n = package_name.lower().strip()
    if not n or n.startswith(("microsoft", "oracle", "sap", "ibm", "adobe", "aws", "azure")):
        return None
    if any(x in n for x in ["windows", "linux", "ubuntu", "debian", "centos", "red hat",
                             "alpine", "freebsd", "macos", "rhel", "fedora", "suse"]):
        return None
    # Python-пакеты
    python_keys = ["fastapi", "uvicorn", "sqlalchemy", "aiohttp", "pandas", "numpy",
                   "pydantic", "starlette", "requests", "httpx", "jinja2", "pyyaml",
                   "openpyxl", "reportlab", "pypdf", "python-docx", "bcrypt", "cryptography",
                   "pyjwt", "python-multipart", "python-dotenv", "psycopg2", "greenlet",
                   "pytest", "black", "flake8", "mypy", "isort", "pylint", "coverage",
                   "tox", "pipenv", "poetry", "click", "rich", "alembic", "passlib",
                   "python-jose", "django", "flask", "scikit-learn", "tensorflow",
                   "pytorch", "keras", "transformers"]
    if any(k == n or n.startswith(k + "-") or n.startswith(k + "_") for k in python_keys):
        return "PyPI"
    if n in ("jinja2", "werkzeug", "markupsafe", "pillow", "lxml", "beautifulsoup4"):
        return "PyPI"
    # JavaScript
    if any(x in n for x in ["react", "vue", "angular", "express", "webpack", "babel",
                             "eslint", "prettier", "axios", "lodash", "jquery", "next",
                             "nuxt", "svelte", "vite", "rollup"]):
        return "npm"
    # Java
    if any(x in n for x in ["spring", "junit", "jackson", "apache", "maven", "lombok",
                             "hibernate", "log4j", "guava", "mockito"]):
        return "Maven"
    # .NET
    if any(x in n for x in ["newtonsoft", "npgsql", "pomelo", "swashbuckle", "serilog",
                             "automapper", "entityframework"]):
        return "NuGet"
    # Go
    if any(x in n for x in ["golang", "gin", "echo", "gorilla"]):
        return "Go"
    return None


async def _fetch_osv_detail(session: aiohttp.ClientSession, vuln_id: str) -> Optional[dict]:
    """Получает детали уязвимости по ID."""
    try:
        url = f"https://api.osv.dev/v1/vulns/{vuln_id}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                data = await resp.json()
                severity = "UNKNOWN"
                for sev in data.get("severity", []):
                    if sev.get("type") == "CVSS_V3":
                        score_str = sev.get("score", "")
                        if score_str:
                            try:
                                cvss_score = float(score_str.split("/")[0]) if "/" in score_str else float(score_str)
                                if cvss_score >= 9.0:
                                    severity = "CRITICAL"
                                elif cvss_score >= 7.0:
                                    severity = "HIGH"
                                elif cvss_score >= 4.0:
                                    severity = "MEDIUM"
                                else:
                                    severity = "LOW"
                            except Exception:
                                pass
                aliases = data.get("aliases", [])
                cve_ids = [a for a in aliases if a.startswith("CVE-")]
                return {
                    "id": vuln_id,
                    "cve": cve_ids[0] if cve_ids else vuln_id,
                    "summary": (data.get("summary") or "")[:200],
                    "severity": severity,
                    "published": (data.get("published") or "")[:10],
                }
    except Exception as e:
        print(f"[OSV] Ошибка получения {vuln_id}: {e}")
    return None


async def check_osv_vulnerabilities(session: aiohttp.ClientSession, components: list) -> dict:
    """Проверяет компоненты на известные уязвимости через OSV API."""
    if not components:
        return {}

    queries = []
    valid_names = []
    for comp in components:
        name = comp.get("name", "").strip()
        version = comp.get("version", "").strip()
        if not name or not version or version == "unknown" or version == "???":
            continue
        ecosystem = _detect_ecosystem(name)
        if ecosystem:
            queries.append({
                "package": {"name": name, "ecosystem": ecosystem},
                "version": version,
            })
            valid_names.append(name)

    if not queries:
        return {}

    try:
        url = "https://api.osv.dev/v1/querybatch"
        async with session.post(url, json={"queries": queries},
                                timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                print(f"[OSV] Ошибка API: {resp.status}")
                return {}
            data = await resp.json()

        results = {}
        for i, item in enumerate(data.get("results", [])):
            vulns = item.get("vulns", [])
            if vulns:
                vuln_details = []
                for v in vulns[:5]:
                    vuln_id = v.get("id", "")
                    detail = await _fetch_osv_detail(session, vuln_id)
                    if detail:
                        vuln_details.append(detail)
                    else:
                        vuln_details.append({"id": vuln_id, "cve": vuln_id,
                                             "summary": "", "severity": "UNKNOWN", "published": ""})
                results[valid_names[i]] = {"count": len(vulns), "vulns": vuln_details}
        return results
    except Exception as e:
        print(f"[OSV] Ошибка проверки: {e}")
        return {}


# ==========================================
# DOCKER-СКАНЕР
# ==========================================
def _check_docker_package_status(name: str) -> tuple:
    name_lower = name.lower().strip()
    if ":" in name_lower:
        name_lower = name_lower.split(":", 1)[0]

    for rule_key, rule in DEFAULT_RULES.items():
        if "❌" not in rule["status"]:
            continue
        rule_key_l = rule_key.lower()
        if len(rule_key_l) <= 4:
            if re.search(r'(?:^|[\.\-_])' + re.escape(rule_key_l) + r'(?:$|[\.\-_])', name_lower):
                return rule["status"], rule.get("recommendation", "")
        else:
            if rule_key_l == name_lower or rule_key_l in name_lower:
                return rule["status"], rule.get("recommendation", "")

    for rule_key, rule in DEFAULT_RULES.items():
        if "Разрешено" in rule["status"] and "⚠️" not in rule["status"] and "❌" not in rule["status"]:
            if rule_key.lower() == name_lower:
                return rule["status"], rule.get("recommendation", "")

    alpine_markers = ("alpine-", "apk-", "busybox", "musl-", "musl.", "scanelf", "ssl_client",
                      "ca-certificates", "aports-", "openrc-", "skalibs-")
    if any(m in name_lower for m in alpine_markers) or name_lower == "zlib":
        return "Разрешено <br><small style='color:#2f855a;'>💡 Системный пакет Alpine Linux</small>", ""

    debian_system = (
        "coreutils", "bash", "dash", "sed", "grep", "gzip", "tar", "hostname",
        "login", "mount", "util-linux", "apt", "dpkg", "adduser",
        "base-files", "base-passwd", "bsdutils", "debianutils",
        "diffutils", "e2fsprogs", "findutils", "gcc-", "gcc-base",
        "logsave", "lsb-base", "mawk", "ncurses", "ncurses-base",
        "ncurses-bin", "passwd", "procps", "ubuntu-keyring",
        "usrmerge", "usermerge", "python3-minimal", "perl-base", "perl-modules", "dpkg-dev",
        "init-system", "debconf", "sysvinit", "systemd", "systemd-",
        "tzdata", "krb5", "gssapi", "ssl-cert", "ca-certificates",
        "openssl", "gnupg", "gpgv", "dirmngr", "sqv", "sq",
        "apt-utils", "apt-transport", "distro-info", "python3", "python3.10",
        "python3.12", "python-apt", "python3-apt", "python3-distutils",
        "python3-pkg-resources", "python3-setuptools", "python3-wheel",
        "libpython3", "libpython3.10", "libpython3.12",
        "init", "initscripts", "ifupdown", "netbase",
        "useradd", "userdel", "users-",
        "xz-utils", "bzip2", "unzip", "zip", "zstd",
        "zlib1g", "zlib1g-dev",
        "iproute2", "iputils", "netcat", "curl", "wget",
        "fdisk", "parted", "e2fslibs", "attr", "acl", "squashfs",
        "locales", "kbd", "console-setup",
    )
    if name_lower.startswith(debian_system):
        return "Разрешено <br><small style='color:#2f855a;'>💡 Системный пакет Ubuntu / Debian</small>", ""

    if name_lower.startswith("lib") or name_lower.startswith("linux-"):
        return "Разрешено <br><small style='color:#2f855a;'>💡 Системная библиотека ОС</small>", ""

    if any(name_lower.endswith(x) for x in ("-dev", "-doc", "-common", "-utils", "-tools", "-base", "-bin", "-data", "-minimal", "-modules", "-dbg")):
        return "Разрешено <br><small style='color:#2f855a;'>💡 Системный компонент</small>", ""

    return "⚠️ Требует внимания", "Не найдено в базе знаний — проверьте вручную"


async def _get_docker_packages(image_name: str) -> list:
    packages = []
    for cmd in [["apk", "list", "--installed"], ["dpkg", "--get-selections"]]:
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "run", "--rm", image_name, *cmd,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
            if proc.returncode == 0:
                output = stdout.decode("utf-8", errors="ignore")
                for line in output.splitlines():
                    parts = line.split()
                    if parts:
                        name = parts[0]
                        ver = parts[1] if len(parts) > 1 else "unknown"
                        status, rec = _check_docker_package_status(name)
                        packages.append({"name": name, "version": ver, "status": status, "recommendation": rec})
                break
        except Exception as e:
            print(f"[DOCKER] Package scan failed ({cmd[0]}): {e}")
            continue
    return packages


async def scan_docker_image(image_name: str) -> dict:
    result = {"image": image_name, "os": "unknown", "os_status": "⚠️ Требует внимания",
              "os_recommendation": "", "packages": [],
              "summary": {"total": 0, "safe": 0, "warn": 0, "danger": 0}, "error": None}
    try:
        check = await asyncio.create_subprocess_exec("docker", "--version",
                                                     stdout=asyncio.subprocess.PIPE,
                                                     stderr=asyncio.subprocess.PIPE)
        await asyncio.wait_for(check.communicate(), timeout=5)
        if check.returncode != 0:
            result["error"] = "Docker недоступен"
            return result
    except Exception:
        result["error"] = "Docker не установлен или недоступен"
        return result

    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "run", "--rm", image_name, "cat", "/etc/os-release",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        if proc.returncode == 0:
            os_info = stdout.decode("utf-8", errors="ignore")
            name_val, version_val = "", ""
            for line in os_info.splitlines():
                if line.startswith("NAME="):
                    name_val = line.split("=", 1)[1].strip('"\'')
                elif line.startswith("VERSION_ID="):
                    version_val = line.split("=", 1)[1].strip('"\'')
            result["os"] = f"{name_val} {version_val}".strip() or "unknown"
        else:
            err = stderr.decode("utf-8", errors="ignore")
            result["error"] = f"Не удалось запустить образ: {err[:300]}"
            return result
    except asyncio.TimeoutError:
        result["error"] = "Таймаут 60 сек: образ не запустился"
        return result
    except Exception as e:
        result["error"] = str(e)
        return result

    os_lower = result["os"].lower()
    banned = ["centos", "red hat", "rhel", "suse", "fedora", "almalinux", "rocky"]
    if any(b in os_lower for b in banned):
        result["os_status"] = "❌ Запрещено"
        result["os_recommendation"] = "Экспортные ограничения. Замените на Astra Linux / ALT Linux / РЕД ОС."
    elif "alpine" in os_lower:
        result["os_status"] = "⚠️ Требует внимания"
        result["os_recommendation"] = "Alpine допустим только в контейнерной среде."
    elif "debian" in os_lower or "ubuntu" in os_lower:
        result["os_status"] = "✅ Разрешено"
        result["os_recommendation"] = "Открытая ОС. Убедитесь в совместимости с российскими ОС."
    elif any(x in os_lower for x in ["astra", "alt", "rosa", "red os"]):
        result["os_status"] = "✅ Разрешено (Российское ПО)"
        result["os_recommendation"] = "Отечественная ОС из Реестра."
    else:
        result["os_status"] = "⚠️ Требует внимания"
        result["os_recommendation"] = f"Не удалось классифицировать ОС '{result['os']}'."

    packages = await _get_docker_packages(image_name)
    result["packages"] = packages[:200]
    safe = sum(1 for p in packages if "Разрешено" in p["status"] and "⚠️" not in p["status"])
    danger = sum(1 for p in packages if "❌" in p["status"])
    result["summary"] = {"total": len(packages), "safe": safe, "danger": danger, "warn": len(packages) - safe - danger}
    return result


# ==========================================
# МОДЕЛИ БАЗЫ ДАННЫХ
# ==========================================
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    session_token = Column(String, unique=True, index=True, nullable=True)
    company_name = Column(String, nullable=False)
    role = Column(String, default="user")
    subscription_plan = Column(String, default="Free")
    subscription_status = Column(String, default="Active")
    free_checks_used = Column(Integer, default=0, nullable=True)
    pro_checks_used = Column(Integer, default=0, nullable=True)
    pro_period_start = Column(DateTime, default=datetime.utcnow, nullable=True)
    is_test = Column(Boolean, default=False, nullable=True)
    last_active = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    reports = relationship("AuditReport", back_populates="owner")


class AuditReport(Base):
    __tablename__ = "audit_reports"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    filename = Column(String, nullable=False)
    status = Column(String, default="pending", nullable=True)
    excel_filename = Column(String, nullable=True)
    report_json = Column(Text, nullable=True)
    verdict_json = Column(Text, nullable=True)
    total_count = Column(Integer, default=0, nullable=True)
    safe_count = Column(Integer, default=0, nullable=True)
    warn_count = Column(Integer, default=0, nullable=True)
    danger_count = Column(Integer, default=0, nullable=True)
    cve_count = Column(Integer, default=0, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User", back_populates="reports")


class LicenseRule(Base):
    __tablename__ = "license_rules"
    id = Column(Integer, primary_key=True, index=True)
    component_key = Column(String, unique=True, index=True, nullable=False)
    license_name = Column(String, nullable=False)
    status = Column(String, nullable=False)
    recommendation = Column(String, nullable=True)


class VisitLog(Base):
    __tablename__ = "visit_logs"
    id = Column(Integer, primary_key=True, index=True)
    path = Column(String, nullable=False)
    ip_address = Column(String, nullable=True)
    visited_at = Column(DateTime, default=datetime.utcnow)


class Feedback(Base):
    __tablename__ = "feedback"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    subject = Column(String, nullable=True)
    message = Column(Text, nullable=False)
    page_url = Column(String, nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class AILicenseCache(Base):
    __tablename__ = "ai_license_cache"
    id = Column(Integer, primary_key=True, index=True)
    component_name = Column(String, unique=True, index=True, nullable=False)
    license = Column(String, nullable=False)
    status = Column(String, nullable=False)
    recommendation = Column(Text, nullable=True)
    provider = Column(String, nullable=True)
    is_failure = Column(Boolean, default=False)
    hit_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)


def run_migrations():
    if not DATABASE_URL.startswith("sqlite"):
        return
    db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
    if not db_path or not os.path.exists(db_path):
        return
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users);")
        user_cols = [c[1] for c in cursor.fetchall()]
        if user_cols:
            for col, sql in [
                ("session_token", "ALTER TABLE users ADD COLUMN session_token VARCHAR;"),
                ("free_checks_used", "ALTER TABLE users ADD COLUMN free_checks_used INTEGER DEFAULT 0;"),
                ("pro_checks_used", "ALTER TABLE users ADD COLUMN pro_checks_used INTEGER DEFAULT 0;"),
                ("pro_period_start", "ALTER TABLE users ADD COLUMN pro_period_start DATETIME;"),
                ("is_test", "ALTER TABLE users ADD COLUMN is_test BOOLEAN DEFAULT 0;"),
            ]:
                if col not in user_cols:
                    cursor.execute(sql)
        cursor.execute("PRAGMA table_info(audit_reports);")
        report_cols = [c[1] for c in cursor.fetchall()]
        if report_cols:
            for col, sql in [
                ("status", "ALTER TABLE audit_reports ADD COLUMN status VARCHAR DEFAULT 'pending';"),
                ("excel_filename", "ALTER TABLE audit_reports ADD COLUMN excel_filename VARCHAR;"),
                ("report_json", "ALTER TABLE audit_reports ADD COLUMN report_json TEXT;"),
                ("verdict_json", "ALTER TABLE audit_reports ADD COLUMN verdict_json TEXT;"),
                ("total_count", "ALTER TABLE audit_reports ADD COLUMN total_count INTEGER DEFAULT 0;"),
                ("safe_count", "ALTER TABLE audit_reports ADD COLUMN safe_count INTEGER DEFAULT 0;"),
                ("warn_count", "ALTER TABLE audit_reports ADD COLUMN warn_count INTEGER DEFAULT 0;"),
                ("danger_count", "ALTER TABLE audit_reports ADD COLUMN danger_count INTEGER DEFAULT 0;"),
                ("cve_count", "ALTER TABLE audit_reports ADD COLUMN cve_count INTEGER DEFAULT 0;"),
            ]:
                if col not in report_cols:
                    cursor.execute(sql)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Migration notice: {e}")


run_migrations()


def sync_rules():
    db = SessionLocal()
    try:
        db.query(LicenseRule).delete()
        db.commit()
        for key, item in DEFAULT_RULES.items():
            key_clean = key.lower().strip()
            db.add(LicenseRule(component_key=key_clean, license_name=item["license"],
                               status=item["status"], recommendation=item.get("recommendation", "")))
        db.commit()
    except Exception as e:
        print(f"Error syncing rules: {e}")
        db.rollback()
    finally:
        db.close()


sync_rules()


def _mark_test_users():
    db = SessionLocal()
    try:
        all_users = db.query(User).all()
        changed = 0
        for u in all_users:
            if u.is_test is None:
                u.is_test = _is_test_email(u.email)
                changed += 1
        if changed:
            db.commit()
            print(f"[MIGRATION] Помечено тестовых: {changed}")
    except Exception as e:
        print(f"[MIGRATION] is_test error: {e}")
        db.rollback()
    finally:
        db.close()


_mark_test_users()


# ==========================================
# УТИЛИТЫ
# ==========================================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get("session_token")
    if not token:
        return None
    user = db.query(User).filter(User.session_token == token).first()
    if user and user.subscription_status != "Blocked":
        user.last_active = datetime.utcnow()
        db.commit()
        return user
    return None


def is_unlimited(user: Optional[User]) -> bool:
    """Безлимит только для администратора. Pro — 50 проверок/месяц."""
    if not user:
        return False
    return user.role == "admin"


def get_free_checks_left(user: Optional[User], request: Request, db: Optional[Session] = None) -> int:
    """Возвращает остаток проверок. Для Pro учитывает 30-дневный период."""
    if user and user.role == "admin":
        return 999

    if user and user.subscription_plan in ["Pro", "Unlimited"]:
        # Сброс счётчика Pro раз в 30 дней
        now = datetime.utcnow()
        period_start = user.pro_period_start or user.created_at or now
        days_passed = (now - period_start).days
        if days_passed >= 30:
            db_local = SessionLocal()
            try:
                db_user = db_local.query(User).filter(User.id == user.id).first()
                if db_user:
                    db_user.pro_checks_used = 0
                    db_user.pro_period_start = now
                    db_local.commit()
                    user.pro_checks_used = 0
                    user.pro_period_start = now
            except Exception as e:
                db_local.rollback()
                print("[PRO RESET] error:", e)
            finally:
                db_local.close()
        used = user.pro_checks_used or 0
        return max(0, PRO_CHECKS_LIMIT - used)

    if user:
        used = user.free_checks_used or 0
        return max(0, FREE_CHECKS_LIMIT - used)
    if request:
        guest_count = int(request.cookies.get("guest_audit_count", 0))
        return max(0, FREE_CHECKS_LIMIT - guest_count)
    return FREE_CHECKS_LIMIT


def _is_test_email(email: str) -> bool:
    """Определяет тестовые email по паттернам."""
    if not email:
        return False
    e = email.lower().strip()
    test_patterns = ["@t.ru", "@test.ru", "@example.ru", "@example.com",
                     "@test.com", "@localhost"]
    if any(e.endswith(p) for p in test_patterns):
        return True
    local = e.split("@")[0]
    if local.startswith(("u", "q", "z", "reg", "test")) and local[-1:].isdigit():
        return True
    return False


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    combined = (password + SECRET_KEY).encode("utf-8")
    pwd_hash = hashlib.pbkdf2_hmac("sha256", combined, salt.encode("utf-8"), 100000).hex()
    return f"pbkdf2${salt}${pwd_hash}"


def verify_password(plain: str, hashed: str) -> bool:
    try:
        parts = hashed.split("$")
        if len(parts) == 3 and parts[0] == "pbkdf2":
            _, salt, pwd_hash = parts
            combined = (plain + SECRET_KEY).encode("utf-8")
            check = hashlib.pbkdf2_hmac("sha256", combined, salt.encode("utf-8"), 100000).hex()
            return secrets.compare_digest(check, pwd_hash)
    except Exception:
        pass
    return False


def sanitize_string(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'[^a-zA-Zа-яА-Я0-9\.\-\+\_/@]', ' ', str(text))
    return re.sub(r'\s+', ' ', text).strip().lower()


def _split_name_version(line: str) -> tuple:
    """Разбирает строку на имя и версию. Поддерживает Maven, npm, pip."""
    line = line.strip()
    if not line:
        return ("", "unknown")

    # Убираем нумерацию в начале: "1. ", "169. "
    line_clean = re.sub(r'^\d+\.\s*', '', line)

    # --- Maven-координаты: group:artifact:jar:version:scope ---
    maven_match = re.match(
        r'^([a-zA-Z0-9_\-\.]+:[a-zA-Z0-9_\-\.]+):(jar|war|pom|aar|bundle):([^:]+):(compile|runtime|test|provided|system)',
        line_clean
    )
    if maven_match:
        name = maven_match.group(1)
        version = maven_match.group(3)
        return (name, version)

    # Упрощённый Maven: group:artifact:version
    maven_simple = re.match(
        r'^([a-zA-Z0-9_\-\.]+:[a-zA-Z0-9_\-\.]+):([\d][^:\s]*)',
        line_clean
    )
    if maven_simple and ':' in maven_simple.group(1):
        return (maven_simple.group(1), maven_simple.group(2))

    # --- npm с em-dash: @scope/package — ^version — npm: ... ---
    if "—" in line_clean or "–" in line_clean:
        parts = re.split(r'\s*[—–]\s*', line_clean)
        if len(parts) >= 2:
            name = parts[0].strip()
            ver_raw = parts[1].strip()
            # Убираем ^ ~ v = из версии
            ver_clean = re.sub(r'^[\^~v=\s]+', '', ver_raw)
            # Если версия начинается с цифры — берём
            ver_match = re.match(r'^([\d][^\s,]*)', ver_clean)
            if ver_match:
                version = ver_match.group(1)
            else:
                version = ver_clean if ver_clean else "unknown"
            if len(name) >= 2:
                return (name, version)

    # --- pip: name==version ---
    m = re.match(r'^([A-Za-z0-9_\-\.]+)\s*(==|>=|<=|~=|!=|>|<|=)\s*([^\s,;#]+)', line_clean)
    if m:
        return m.group(1).strip(), m.group(3).strip()

    # --- Формат "name: version" ---
    m = re.match(r'^["\']?([A-Za-z0-9_\-\.@/]+)["\']?\s*:\s*["\']?[\^~v=]?([\d][^\s,;"\']*)', line_clean)
    if m:
        return m.group(1).strip(), m.group(2).strip()

    # --- Fallback: возвращаем всю строку как имя, версия unknown ---
    # Если в строке есть цифры в конце — попробуем извлечь как версию
    m = re.match(r'^([^\d]+?)\s+([\d][\d\.\-\w]*)$', line_clean)
    if m:
        name = m.group(1).strip()
        ver = m.group(2).strip()
        if len(name) >= 2:
            return (name, ver)
    # Иначе — вся строка как имя
    return (line_clean, "unknown")


def _is_private_library(name: str) -> bool:
    """Определяет私有 библиотеки компании."""
    n = (name or "").lower().strip()
    if not n:
        return False
    private_markers = [
        "ru.logic.bpm", "logicbpm", "@logicbpm", "logic.bpm",
        "tenant-encryption", "tenant-interceptor", "tenant-kafka",
        "tenant-security", "tenant-storage",
        "archive.adminapi", "archive.bl", "archive.cryptography",
    ]
    return any(marker in n for marker in private_markers)


def _is_license_like(text: str) -> bool:
    """Проверяет, похоже ли значение на название лицензии, а не на версию."""
    if not text:
        return False
    t = str(text).strip().lower()
    if not t or t == "unknown":
        return False
    license_markers = [
        "mit", "apache", "bsd", "gpl", "lgpl", "mpl", "epl",
        "isc", "cc0", "cc-by", "unlicense", "public domain",
        "proprietary", "commercial", "eula", "sspl", "bsl",
        "artistic", "cddl", "zlib", "wtfpl", "agpl",
    ]
    if t in license_markers:
        return True
    for m in license_markers:
        if t.startswith(m) or t.endswith(m):
            return True
    # Если строка не содержит цифр — вряд ли это версия
    if not any(c.isdigit() for c in t):
        return True
    return False


def _is_garbage_component(name: str) -> bool:
    """Отсеивает авторов, пространства имён и метаданные."""
    if not name:
        return True
    n = name.strip()
    if len(n) < 2:
        return True
    if n.startswith('['):
        return True
    if "," in n and len(n.split(",")) > 1:
        return True
    # Имена людей: два-три слова с заглавной буквы (не название)
    words = n.split()
    if 2 <= len(words) <= 3:
        if all(w[0].isupper() for w in words if w):
            # Проверить, что это не название продукта
            product_markers = [
                "server", "windows", "linux", "oracle", "microsoft", "ibm",
                "sap", "adobe", "amazon", "google", "docker", "kubernetes",
                "red hat", "enterprise", "community", "edition", "runtime",
                "toolkit", "framework", "python", "java", "node", "npm",
                "apache", "nginx", "postgres", "mysql", "redis", "kafka",
                "grafana", "zabbix", "prometheus", "unity", "unreal",
                "active", "director", "visual", "studio", "source",
                "git", "gitlab", "jenkins", "teamcity", "sonar",
                "hashicorp", "vault", "consul", "nomad", "boundary",
                "elastic", "opensearch", "fluent", "opentelemetry",
                "py", "torch", "tensor", "flow", "open", "policy",
            ]
            lower = n.lower()
            if not any(m in lower for m in product_markers):
                return True
    lower = n.lower()
    if lower.startswith(("author", "copyright", "company", "namespace", "project",
                          "creator", "maintainer", "owner", "publisher")):
        return True
    if lower in ("name", "название", "компонент", "component"):
        return True
    # Заголовки и разделы документа
    headers = (
        "оглавление", "содержание", "frontend", "backend", "введение",
        "пояснительная", "заключение", "приложение", "раздел", "глава",
        "список", "перечень", "описание", "аннотация", "титульный",
        "table of contents", "contents", "introduction", "conclusion",
        "appendix", "chapter", "section", "list of",
    )
    if any(lower.startswith(h) for h in headers):
        return True
    # Пронумерованные заголовки
    if re.match(r'^\d+\.\s+[А-ЯA-Z]', n):
        rest = re.sub(r'^\d+\.\s+', '', n)
        if len(rest.split()) > 3:
            return True
    # Многоточия из оглавления
    if "..." in n or " . . " in n or "…" in n:
        return True
    # Слишком длинные строки
    if len(n) > 100:
        return True
    # Номер страницы в конце длинной строки
    if re.search(r'\s+\d+$', n) and len(n.split()) > 2:
        return True
    # Только число
    if re.match(r'^\d+$', n):
        return True
    # Приватные/служебные строки
    if lower.startswith(("дополненная", "указанные", "таким образом", "в ходе", "в составе")):
        return True
    # URL
    if lower.startswith(("http://", "https://", "www.")):
        return True
    # Строки с "для установки", "this document"
    if "для установки" in lower or "this document" in lower:
        return True
    # Длинные предложения (абзацы из PDF) — не компоненты
    if len(n.split()) > 6:
        return True
    # Строки с кавычками и типичным «текстовым» содержимым
    if any(marker in lower for marker in [
        "указанием", "функционировании", "разработке", "продукта",
        "компании", "публичных", "распространяемые", "перечень",
        "применённых", "описание", "используемых", "настоящий",
        "представлен", "приведен", "включает",
    ]):
        return True
    # Строки, начинающиеся с маленькой буквы или части слова (обрывки)
    if n and n[0].islower() and len(n.split()) > 2:
        return True
    # Строки с "»" или "«" в начале/конце (цитаты из PDF)
    if n.startswith(("»", "«")) or n.endswith(("»", "«")) or n.startswith("помощник"): 
        return True
    # Заголовки таблиц: name + version + license (+ source)
    table_headers = [
        "name version license",
        "name version license source",
        "компонент версия лицензия",
        "компонент версия лицензия правообладатель",
        "наименование версия лицензия",
    ]
    if any(lower.startswith(h) for h in table_headers):
        return True
    # Строки про "версия программного продукта"
    if lower.startswith(("версия программного продукта", "версия по", "программное обеспечение")):
        return True
    return False


def _parse_license_doc_line(line: str):
    """
    Парсит строку формата "Название (Лицензия)" или "Название ([Лицензия](url))".
    Возвращает (name, license) или None.
    """
    line = line.strip()
    if not line:
        return None
    line = line.rstrip(".")

    # Приоритет 1: Markdown-формат [License Text](url)
    md_groups = re.findall(r'\[([^\]]+)\]\([^)]+\)', line)
    if md_groups:
        license_keywords = [
            "license", "licence", "gpl", "lgpl", "mit", "bsd", "apache",
            "mozilla", "mpl", "epl", "cddl", "isc", "artistic",
            "public domain", "psf", "python", "openssl", "curl",
            "openldap", "лиценз", "соглашение", "zero clause",
            "exception", "runtime", "foundation",
        ]
        license_text = None
        for g in reversed(md_groups):
            g_lower = g.lower()
            g_stripped = g.strip()
            if len(g_stripped) <= 5 and not any(k in g_lower for k in ["mit", "bsd", "gpl", "apache"]):
                continue
            if any(k in g_lower for k in license_keywords):
                license_text = g_stripped
                break
        if license_text:
            name_match = re.match(r'^([^\[(]+?)\s*[\(\[]', line)
            if name_match:
                name = name_match.group(1).strip()
                if len(name) >= 2:
                    return (name, license_text)

    # Приоритет 2: Круглые скобки (Nazvanie (License))
    groups = re.findall(r'\(([^()]+)\)', line)
    if groups:
        license_keywords = [
            "license", "licence", "gpl", "lgpl", "mit", "bsd", "apache",
            "mozilla", "mpl", "epl", "cddl", "isc", "artistic",
            "public domain", "psf", "python", "openssl", "curl",
            "openldap", "лиценз", "соглашение", "zero clause",
            "exception", "runtime", "foundation",
        ]
        license_text = None
        for g in reversed(groups):
            g_lower = g.lower()
            g_stripped = g.strip()
            if len(g_stripped) <= 5 and not any(k in g_lower for k in ["mit", "bsd", "gpl", "apache"]):
                continue
            if any(k in g_lower for k in license_keywords):
                license_text = g_stripped
                break
        if license_text:
            name_match = re.match(r'^([^(]+?)\s*\(', line)
            if name_match:
                name = name_match.group(1).strip()
                if len(name) >= 2:
                    return (name, license_text)

    return None


def _clean_markdown(text: str) -> str:
    """Убирает markdown-разметку: [текст](url) → текст, **жирный** → жирный."""
    if not text:
        return text
    # [текст](url) → текст
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # **текст** → текст
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    # *текст* → текст (курсив, но осторожно с умножением)
    text = re.sub(r'(?<![\w*])\*([^*\n]+)\*(?![\w*])', r'\1', text)
    # `код` → код
    text = re.sub(r'`([^`]+)`', r'\1', text)
    return text.strip()


def _is_section_header(line: str) -> bool:
    """Определяет заголовки разделов документа."""
    line = line.strip()
    if not line or "(" in line:
        return False
    headers = [
        "операционная система",
        "компиляторы и средства сборки",
        "среда выполнения",
        "система управления базами данных",
        "обмен сообщениями",
        "сетевые компоненты",
        "криптография",
        "системные библиотеки",
        "аудиоподсистема",
        "средства администрирования",
        "мониторинг",
        "библиотеки исполнения",
        "среда выполнения python",
    ]
    lower = line.lower()
    return any(lower.startswith(h) for h in headers)


def parse_uploaded_file(file_bytes: bytes, filename: str) -> list:
    extracted = []
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    try:
        if ext in ["xlsx", "xls"]:
            xl = pd.ExcelFile(io.BytesIO(file_bytes))
            for sheet in xl.sheet_names:
                df = xl.parse(sheet, header=None)
                for _, row in df.iterrows():
                    row_vals = [str(v).strip() for v in row.values if pd.notna(v)]
                    if row_vals:
                        name = row_vals[0]
                        ver = row_vals[1] if len(row_vals) > 1 else "unknown"
                        if not _is_garbage_component(name):
                            extracted.append({"name": name, "version": ver})
        elif ext == "docx":
            doc = docx.Document(io.BytesIO(file_bytes))
            # Обработка таблиц (как было)
            for table in doc.tables:
                for row in table.rows:
                    row_vals = [c.text.strip() for c in row.cells if c.text.strip()]
                    if row_vals:
                        name = row_vals[0]
                        ver = row_vals[1] if len(row_vals) > 1 else "unknown"
                        if not _is_garbage_component(name):
                            extracted.append({"name": name, "version": ver})
            # Обработка параграфов с поддержкой лицензий
            for p in doc.paragraphs:
                raw = p.text.strip()
                if not raw:
                    continue
                # Убираем markdown-разметку
                line = _clean_markdown(raw)
                if not line:
                    continue
                # Пропускаем заголовки разделов
                if _is_section_header(line):
                    continue
                # Пробуем формат "Название (Лицензия)" / "Название ([License](url))"
                license_doc = _parse_license_doc_line(raw)
                if not license_doc:
                    license_doc = _parse_license_doc_line(line)
                if license_doc:
                    name, lic = license_doc
                    extracted.append({
                        "name": name,
                        "version": "unknown",
                        "_license": lic,
                    })
                    continue
                # Обычная обработка — "name: version" или просто "name"
                parts = re.split(r'[\t:,]+', line)
                if parts and parts[0] and not _is_garbage_component(parts[0]):
                    extracted.append({
                        "name": parts[0].strip(),
                        "version": parts[1].strip() if len(parts) > 1 else "unknown",
                    })
        elif ext == "json":
            data = json.loads(file_bytes.decode("utf-8", errors="ignore"))
            if "components" in data:
                for comp in data.get("components", []):
                    if comp.get("name") and not _is_garbage_component(comp["name"]):
                        extracted.append({"name": comp["name"], "version": comp.get("version", "unknown")})
            elif "dependencies" in data:
                for dep, ver in data.get("dependencies", {}).items():
                    if not _is_garbage_component(dep):
                        extracted.append({"name": dep, "version": str(ver)})
        elif ext == "pdf":
            # Извлекаем текст из всех страниц PDF
            pdf_reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            full_text = ""
            for page in pdf_reader.pages:
                try:
                    page_text = page.extract_text() or ""
                    full_text += page_text + "\n"
                except Exception as pe:
                    print(f"[PDF] Ошибка страницы: {pe}")

            # Собираем статистику по строкам (для поиска повторяющихся)
            lines_raw = [ln.strip() for ln in full_text.splitlines()]
            from collections import Counter
            line_counter = Counter([ln for ln in lines_raw if len(ln) >= 5])
            # Повторяющиеся больше 3 раз — это колонтитулы, пропускаем
            repeated_lines = {ln for ln, cnt in line_counter.items() if cnt >= 3}

            seen_names = set()
            for line in lines_raw:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Очень короткие строки (1-4 символа) — пропустить
                if len(line) < 5:
                    continue
                # Только цифры (номер страницы)
                if re.match(r'^\d+$', line):
                    continue
                # Строка из точек/пробелов (оглавление)
                if re.match(r'^[\s\.\u2026]+$', line):
                    continue
                # Строка с многоточием и цифрой в конце (оглавление)
                if re.search(r'\.\s*\.\s*\.', line) and re.search(r'\d+\s*$', line):
                    continue
                # Повторяющаяся строка (колонтитул)
                if line in repeated_lines:
                    continue
                # Строка с "Оглавление" / "Содержание" / "стр."
                lower = line.lower()
                if lower.startswith(("оглавление", "содержание", "стр.", "страница", "page ")):
                    continue
                # Строка вида "1. FRONTEND . . . 3" (оглавление с номером страницы)
                if re.match(r'^\d+\.\s+\S+', line) and re.search(r'\.{2,}', line):
                    continue
                # Строка вида "1" или "12" в конце (уже отфильтровано выше)
                # Разбираем на name + version
                name, ver = _split_name_version(line)
                if not name or len(name) < 3:
                    continue
                if _is_garbage_component(name):
                    continue
                # Дедупликация
                key = name.lower().strip()
                if key in seen_names:
                    continue
                seen_names.add(key)
                extracted.append({"name": name, "version": ver})
        else:
            text = file_bytes.decode("utf-8", errors="ignore")
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # Пропускаем заголовки разделов
                if _is_section_header(line):
                    continue

                # Пробуем формат "Название (Лицензия)"
                license_doc = _parse_license_doc_line(line)
                if license_doc:
                    name, lic = license_doc
                    # Не фильтруем — если строка попала в формат "Название (Лицензия)",
                    # значит, это уже валидный компонент
                    extracted.append({
                        "name": name,
                        "version": "unknown",
                        "_license": lic,
                    })
                    continue

                # Обычный формат "name==version"
                name, ver = _split_name_version(line)
                if not _is_garbage_component(name):
                    extracted.append({"name": name, "version": ver})
    except Exception as e:
        print(f"Parse error {filename}: {e}")
    # Нормализация: если "версия" на самом деле лицензия — сбрасываем
    for item in extracted:
        if _is_license_like(item.get("version", "")):
            item["version"] = "unknown"
    # Пометка приватных библиотек
    for item in extracted:
        if _is_private_library(item.get("name", "")):
            item["_private"] = True
            item["license"] = "Собственная разработка"
            item["status"] = "✅ Разрешено <br><small style='color:#2f855a;'>💡 Собственная разработка компании (не в публичных реестрах)</small>"
    # Дедупликация по имени (без учёта регистра)
    seen = set()
    unique = []
    for item in extracted:
        key = (item.get("name") or "").lower().strip()
        if key and key not in seen:
            seen.add(key)
            unique.append(item)
    extracted = unique
    if not extracted:
        extracted = [{"name": filename.split(".")[0], "version": "1.0.0"}]
    return extracted


async def fetch_package_info_with_version(session, package_name, table_version, cached_rules,
                                          report_id, ai_provider="auto", pre_license=None) -> dict:
    search_clean = sanitize_string(package_name)

    # Если лицензия уже извлечена из документа — используем её без ИИ
    if pre_license:
        lic_lower = pre_license.lower()
        # Определяем статус по ключевым словам в лицензии
        forbidden_markers = [
            "proprietary", "commercial", "eula", "nvidia", "oracle",
            "microsoft", "aws", "google cloud", "sspl", "bsl",
        ]
        attention_markers = [
            "gpl-3", "gplv3", "agpl", "lgpl", "mpl", "busl", "sspl",
            "openjdk", "gpl-2", "gplv2",
        ]
        if any(m in lic_lower for m in forbidden_markers):
            status = "⚠️ Требует внимания"
        elif any(m in lic_lower for m in attention_markers):
            status = "Разрешено с условиями"
        else:
            status = "✅ Разрешено"
        return {
            "name": package_name,
            "version": table_version,
            "license": pre_license,
            "status": f"{status} <br><small style='color:#4a5568;'>💡 Лицензия из документа</small>",
        }

    # Приватные библиотеки — сразу возвращаем результат без ИИ
    if _is_private_library(package_name):
        return {"name": package_name, "version": table_version,
                "license": "Собственная разработка",
                "status": "✅ Разрешено <br><small style='color:#2f855a;'>💡 Собственная разработка компании</small>"}


    if any(re.search(r'\b' + re.escape(ide) + r'\b', search_clean)
           for ide in ["visual studio code", "vscode", "vscodium", "intellij idea", "pycharm", "webstorm", "eclipse", "netbeans"]):
        return {"name": package_name, "version": table_version, "license": "MIT / Apache-2.0 / EULA",
                "status": "Разрешено <br><small style='color:#2f855a;'>💡 IDE не поставляется в составе ПО</small>"}

    if any(re.search(r'\b' + re.escape(k) + r'\b', search_clean) for k in ["cuda", "nvidia"]):
        return {"name": package_name, "version": table_version, "license": "NVIDIA Proprietary",
                "status": "❌ Запрещено <br><small style='color:#e53e3e;'>💡 Привязка к оборудованию вендора</small>"}

    if "devexpress" in search_clean or "dev express" in search_clean:
        return {"name": package_name, "version": table_version,
                "license": "Commercial / DevExpress EULA",
                "status": "❌ Запрещено <br><small style='color:#e53e3e;'>💡 Экспортные ограничения. Замена: открытые UI-библиотеки</small>"}

    # ============================================================
    # ХАРДКОД: компоненты из таблицы Минцифры (100% надёжно)
    # ============================================================

    # DevExpress (все модули)
    if "devexpress" in search_clean or "dev express" in search_clean or "devart" in search_clean:
        return {"name": package_name, "version": table_version,
                "license": "Commercial / DevExpress EULA",
                "status": "❌ Запрещено <br><small style='color:#e53e3e;'>💡 Экспортные ограничения. Замена: открытые UI-библиотеки</small>"}

    # .NET SDK (с версией в названии)
    if ".net sdk" in search_clean or "dotnet sdk" in search_clean or search_clean.startswith(".net "):
        return {"name": package_name, "version": table_version,
                "license": "MIT",
                "status": "✅ Разрешено <br><small style='color:#2f855a;'>💡 .NET SDK — MIT</small>"}

    # Elastic Beats (Filebeat, Metricbeat и др.) — запрещены
    if "filebeat" in search_clean or "metricbeat" in search_clean or "packetbeat" in search_clean or "auditbeat" in search_clean or "elastic beats" in search_clean:
        return {"name": package_name, "version": table_version,
                "license": "Elastic License 2.0",
                "status": "❌ Запрещено <br><small style='color:#e53e3e;'>💡 Elastic License. Замена: Fluent Bit / OpenSearch</small>"}

    # Fluent Bit / Fluentd
    if "fluent bit" in search_clean or "fluentbit" in search_clean or "fluent-bit" in search_clean or "fluentd" in search_clean:
        return {"name": package_name, "version": table_version,
                "license": "Apache-2.0",
                "status": "✅ Разрешено <br><small style='color:#2f855a;'>💡 Fluent Bit / Fluentd — Apache-2.0</small>"}

    # Jaeger
    if "jaeger" in search_clean:
        return {"name": package_name, "version": table_version,
                "license": "Apache-2.0",
                "status": "✅ Разрешено <br><small style='color:#2f855a;'>💡 Jaeger — Apache-2.0</small>"}

    # Oracle MySQL — различаем Community (разрешено) и Commercial (запрещено)
    if "mysql" in search_clean:
        if "community" in search_clean:
            return {"name": package_name, "version": table_version,
                    "license": "GPL-2.0",
                    "status": "✅ Разрешено <br><small style='color:#2f855a;'>💡 MySQL Community Edition — открытая лицензия (GPL)</small>"}
        elif "oracle" in search_clean or "enterprise" in search_clean or "cluster" in search_clean:
            return {"name": package_name, "version": table_version,
                    "license": "Commercial / Proprietary",
                    "status": "❌ Запрещено <br><small style='color:#e53e3e;'>💡 Oracle MySQL (Commercial). Замена: MySQL Community / MariaDB / Postgres Pro</small>"}

    # Запрещённые СУБД
    banned_db = [
        ("ibm db2", "IBM DB2"),
        ("db2", "IBM DB2"),
        ("intersystems", "InterSystems Caché"),
        ("splunk", "Splunk"),
        ("sap ase", "SAP ASE"),
        ("sybase", "Sybase"),
        ("sap sql anywhere", "SAP SQL Anywhere"),
        ("sap hana", "SAP HANA"),
        ("oracle nosql", "Oracle NoSQL"),
        ("oracle database", "Oracle Database"),
    ]
    for key, label in banned_db:
        if key in search_clean:
            return {"name": package_name, "version": table_version,
                    "license": "Commercial / Proprietary",
                    "status": f"❌ Запрещено <br><small style='color:#e53e3e;'>💡 {label}. Замена: Postgres Pro / MariaDB</small>"}

    # Запрещённые серверы приложений
    banned_app_servers = [
        ("websphere", "IBM WebSphere"),
        ("weblogic", "Oracle WebLogic"),
        ("jboss", "Red Hat JBoss EAP"),
        ("coldfusion", "Adobe ColdFusion"),
        ("netweaver", "SAP NetWeaver"),
        ("zend server", "RogueWave Zend Server"),
    ]
    for key, label in banned_app_servers:
        if key in search_clean:
            return {"name": package_name, "version": table_version,
                    "license": "Commercial / Proprietary",
                    "status": f"❌ Запрещено <br><small style='color:#e53e3e;'>💡 {label}. Замена: WildFly / TomEE</small>"}

    # Запрещённые платформы
    banned_platforms = [
        ("filenet", "IBM FileNet"),
        ("lotus domino", "IBM Lotus Domino"),
        ("lotus notes", "IBM Lotus Notes"),
    ]
    for key, label in banned_platforms:
        if key in search_clean:
            return {"name": package_name, "version": table_version,
                    "license": "Commercial / Proprietary",
                    "status": f"❌ Запрещено <br><small style='color:#e53e3e;'>💡 {label}.</small>"}

    # Запрещённые ОС
    banned_os = [
        ("redhat", "Red Hat Enterprise Linux"),
        ("red hat", "Red Hat Enterprise Linux"),
        ("suse linux", "SUSE Linux Enterprise"),
        ("sles", "SUSE Linux Enterprise Server"),
    ]
    for key, label in banned_os:
        if key in search_clean:
            return {"name": package_name, "version": table_version,
                    "license": "Commercial / Proprietary",
                    "status": f"❌ Запрещено <br><small style='color:#e53e3e;'>💡 {label}. Замена: Astra Linux / ALT Linux</small>"}

    # Разрешённые серверы приложений (open-source из таблицы Минцифры)
    allowed_app_servers = [
        ("wildfly", "WildFly", "LGPL-2.1"),
        ("tomee", "Apache TomEE", "Apache-2.0"),
        ("geronimo", "Apache Geronimo", "Apache-2.0"),
        ("glassfish", "GlassFish", "CDDL / GPL"),
        ("resin", "Resin", "GPL / Commercial"),
    ]
    for key, label, lic in allowed_app_servers:
        if key in search_clean:
            return {"name": package_name, "version": table_version,
                    "license": lic,
                    "status": f"✅ Разрешено <br><small style='color:#2f855a;'>💡 {label} — открытая лицензия</small>"}

    # EnterpriseDB — принудительно запрещено (таблица Минцифры)
    if "enterprisedb" in search_clean or "edb postgres" in search_clean or search_clean == "edb":
        return {"name": package_name, "version": table_version,
                "license": "Commercial / Proprietary",
                "status": "❌ Запрещено <br><small style='color:#e53e3e;'>💡 EnterpriseDB — коммерческая редакция. Замена: Postgres Pro</small>"}

    # Разрешённые СУБД и серверы приложений из таблицы Минцифры
    allowed_db_app = [
        ("couchdb", "Apache CouchDB", "Apache-2.0"),
        ("hive", "Apache Hive", "Apache-2.0"),
        ("tibero", "TmaxSoft Tibero", "Commercial (Южная Корея)"),
        ("libercat", "Libercat", "Российское ПО"),
        ("enhydra", "Enhydra Server", "Open Source"),
    ]
    for key, label, lic in allowed_db_app:
        if key in search_clean:
            return {"name": package_name, "version": table_version,
                    "license": lic,
                    "status": f"✅ Разрешено <br><small style='color:#2f855a;'>💡 {label} — открытая лицензия</small>"}

    # Oracle MySQL Community (открытая) vs Commercial (запрещена)
    if "mysql" in search_clean and "community" in search_clean:
        return {"name": package_name, "version": table_version,
                "license": "GPL-2.0",
                "status": "✅ Разрешено <br><small style='color:#2f855a;'>💡 MySQL Community Edition — открытая лицензия</small>"}

    # Разрешённые СУБД (open-source из таблицы Минцифры)
    if "firebird" in search_clean:
        return {"name": package_name, "version": table_version,
                "license": "Interbase Public License",
                "status": "✅ Разрешено <br><small style='color:#2f855a;'>💡 Firebird — открытая лицензия</small>"}

    # ============================================================

    if any(re.search(r'\b' + re.escape(e) + r'\b', search_clean) for e in ["elasticsearch", "kibana", "logstash"]):
        return {"name": package_name, "version": table_version, "license": "SSPL / Elastic License",
                "status": "❌ Запрещено <br><small style='color:#e53e3e;'>💡 Санкционные риски. Замена: OpenSearch</small>"}

    gcp_keywords = ["firebase", "google-cloud", "google-api", "google-auth", "googleapis",
                    "google-crc32c", "google-resumable-media"]
    if any(k in search_clean for k in gcp_keywords) or re.search(r'\bgoogle\b', search_clean):
        return {"name": package_name, "version": table_version,
                "license": "Apache-2.0 (SDK) / Proprietary Service",
                "status": "❌ Запрещено <br><small style='color:#e53e3e;'>💡 Google Cloud. Замена: PostgreSQL / MinIO</small>"}

    if any(re.search(r'\b' + re.escape(a) + r'\b', search_clean) for a in ["boto3", "botocore", "s3transfer"]):
        return {"name": package_name, "version": table_version, "license": "Apache-2.0",
                "status": "❌ Запрещено <br><small style='color:#e53e3e;'>💡 AWS SDK. Замена: MinIO SDK</small>"}

    rus_software = {
        "astra linux": ("Commercial / FSTEC", "✅ Разрешено (Российское ПО)", "Astra Linux (реестр №369)"),
        "alt linux": ("GPL / Certificate", "✅ Разрешено (Российское ПО)", "ALT Linux (реестр №1541)"),
        "ред ос": ("Commercial / FSTEC", "✅ Разрешено (Российское ПО)", "РЕД ОС (реестр №3751)"),
        "red os": ("Commercial / FSTEC", "✅ Разрешено (Российское ПО)", "РЕД ОС (реестр №3751)"),
        "роса": ("Commercial / FSTEC", "✅ Разрешено (Российское ПО)", "РОСА (реестр №1610)"),
        "rosa": ("Commercial / FSTEC", "✅ Разрешено (Российское ПО)", "РОСА (реестр №1610)"),
        "postgres pro": ("Commercial", "✅ Разрешено (Российское ПО)", "Postgres Pro (реестр №104)"),
        "postgrespro": ("Commercial", "✅ Разрешено (Российское ПО)", "Postgres Pro (реестр №104)"),
        "криптопро": ("Commercial", "✅ Разрешено (Российское ПО)", "КриптоПро CSP (реестр №2855)"),
        "cryptopro": ("Commercial", "✅ Разрешено (Российское ПО)", "КриптоПро CSP (реестр №2855)"),
        "ред база данных": ("Commercial", "✅ Разрешено (Российское ПО)", "Ред База Данных (реестр №3383)"),
        "liberica": ("Commercial / BellSoft", "✅ Разрешено (Российское ПО)", "Liberica JDK (реестр №5493)"),
        "axiom": ("Commercial / ФСТЭК", "✅ Разрешено (Российское ПО)", "Axiom JDK (реестр №17783)"),
        "динамика jdk": ("Commercial / Для КИИ", "✅ Разрешено (Российское ПО)", "Динамика JDK (реестр №31332)"),
    }
    for rus_key, (lic, st, rec) in rus_software.items():
        if re.search(r'\b' + re.escape(rus_key) + r'\b', search_clean) or rus_key in search_clean:
            return {"name": package_name, "version": table_version, "license": lic,
                    "status": f"{st} <br><small style='color:#2f855a;'>🇷🇺 {rec}</small>"}

    java_keywords = ["openjdk", "oracle jdk", "temurin", "corretto", "zulu", "jdk"]
    is_foreign_java = any(re.search(r'\b' + re.escape(j) + r'\b', search_clean) for j in java_keywords)
    if not is_foreign_java and re.search(r'\bjava\b', search_clean) and not re.search(r'\bjavascript\b', search_clean):
        is_foreign_java = True
    if is_foreign_java:
        return {"name": package_name, "version": table_version,
                "license": "GPL-2.0 with CE / Proprietary",
                "status": "⚠️ Требует внимания <br><small style='color:#dd6b20;'>💡 Liberica JDK (№5493), Axiom JDK (№17783) или Динамика JDK (№31332)</small>"}

    if "mongodb" in search_clean:
        return {"name": package_name, "version": table_version, "license": "SSPL",
                "status": "⚠️ Требует внимания <br><small style='color:#dd6b20;'>💡 SSPL. Замена: PostgresPro</small>"}
    if "redis" in search_clean and "valkey" not in search_clean:
        return {"name": package_name, "version": table_version,
                "license": "RSALv2 / SSPL / BSD (до 7.2)",
                "status": "⚠️ Требует внимания <br><small style='color:#dd6b20;'>💡 С 7.4 — SSPL/RSALv2. Замена: Valkey</small>"}

    if any(re.search(r'\b' + re.escape(os_key) + r'\b', search_clean)
           for os_key in ["centos", "red hat", "rhel", "suse", "windows", "macos", "almalinux", "rocky linux", "fedora", "opensuse"]):
        return {"name": package_name, "version": table_version,
                "license": "Иностранная ОС / EULA",
                "status": "❌ Запрещено <br><small style='color:#e53e3e;'>💡 Экспортные ограничения</small>"}

    if re.search(r'\bubuntu\b', search_clean):
        return {"name": package_name, "version": table_version,
                "license": "GPL / Canonical",
                "status": "Разрешено с условиями <br><small style='color:#2b6cb0;'>💡 Условно. Требуется совместимость с 2 российскими ОС</small>"}

    if any(re.search(r'\b' + re.escape(o) + r'\b', search_clean)
           for o in ["debian", "mandriva", "gentoo", "freebsd", "mint", "openbsd", "slackware"]):
        return {"name": package_name, "version": table_version,
                "license": "GPL / Открытая лицензия",
                "status": "Разрешено <br><small style='color:#2f855a;'>💡 Соответствует требованиям</small>"}

    matched_rule = None
    all_rules = list(cached_rules)
    for k, v in DEFAULT_RULES.items():
        all_rules.append({"component_key": k, "license_name": v["license"],
                          "status": v["status"], "recommendation": v.get("recommendation", "")})
    all_rules.sort(key=lambda x: len(x.get("component_key", "")), reverse=True)

    for rule in all_rules:
        rule_key = rule.get("component_key", "").lower().strip()
        if not rule_key or len(rule_key) < 2:
            continue
        try:
            if re.search(r'\b' + re.escape(rule_key) + r'\b', search_clean):
                matched_rule = rule
                break
        except re.error:
            if rule_key in search_clean:
                matched_rule = rule
                break

    if matched_rule:
        status_text = matched_rule["status"]
        if matched_rule.get("recommendation"):
            status_text += f" <br><small style='color:#d69e2e;'>💡 {matched_rule['recommendation']}</small>"
        return {"name": package_name, "version": table_version,
                "license": f"{matched_rule['license_name']} (База знаний)",
                "status": status_text}

    ai_lic, ai_status, ai_rec = await ask_ai_for_license(package_name, provider=ai_provider)
    return {"name": package_name, "version": table_version,
            "license": f"{ai_lic} (AI)",
            "status": f"{ai_status} <br><small style='color:#3182ce;'>🤖 {ai_rec}</small>"}


def _build_verdict(report_data: list) -> dict:
    critical = [i for i in report_data if "❌ Запрещено" in str(i.get("status", ""))]
    warning = [i for i in report_data if "⚠️ Требует внимания" in str(i.get("status", ""))]

    # Добавляем компоненты с уязвимостями в предупреждения
    cve_items = [i for i in report_data if i.get("cve_count", 0) > 0]
    for cve_item in cve_items:
        if cve_item not in warning and cve_item not in critical:
            warning.append(cve_item)

    has_game_engine = any(
        "unity" in str(i.get("name", "")).lower() or "unreal" in str(i.get("name", "")).lower()
        for i in warning
    )

    if critical:
        verdict = "❌ НЕ ПРОЙДЁТ РЕЕСТР"
        reason = f"Обнаружено {len(critical)} запрещённых компонент(ов), блокирующих включение в Единый реестр. Требуется обязательная замена."
    elif warning:
        verdict = "⚠️ МОЖЕТ ПРОЙТИ С ЗАМЕЧАНИЯМИ"
        reason = f"Обнаружено {len(warning)} компонент(ов), требующих внимания. Возможен отказ экспертного совета."
        if cve_items:
            total_cve = sum(i.get("cve_count", 0) for i in cve_items)
            reason += f" ВНИМАНИЕ: Найдено {total_cve} уязвимостей в {len(cve_items)} компонент(ах). Рекомендуется обновление."
        if has_game_engine:
            reason += " Обнаружены компоненты Unity/Unreal Engine. Включение возможно только как временная мера (Письмо Минцифры от 21.08.2023 № АЗ-П11-4-200-216747)."
    else:
        verdict = "✅ СООТВЕТСТВУЕТ ТРЕБОВАНИЯМ"
        reason = "Запрещённых компонентов и уязвимостей не обнаружено. Продукт соответствует ПП РФ № 1236."

    return {"verdict": verdict, "reason": reason,
            "critical_count": len(critical), "warning_count": len(warning),
            "critical_list": [i.get("name", "") for i in critical][:20],
            "warning_list": [i.get("name", "") for i in warning][:20],
            "cve_total": sum(i.get("cve_count", 0) for i in cve_items)}


async def process_audit_task(report_id: int, file_bytes: bytes, filename: str, is_pro: bool, ai_provider: str = "auto"):
    db = SessionLocal()
    try:
        parsed = await asyncio.to_thread(parse_uploaded_file, file_bytes, filename)
        total_parsed = len(parsed)
        items = parsed[:FREE_COMPONENTS_LIMIT] if (not is_pro and total_parsed > FREE_COMPONENTS_LIMIT) else parsed

        PROGRESS_TRACKER[report_id] = {"total": len(items), "processed": 0, "cancel": False}

        rules = db.query(LicenseRule).all()
        cached_rules = [{"component_key": r.component_key.lower().strip(),
                         "license_name": r.license_name, "status": r.status,
                         "recommendation": r.recommendation} for r in rules if r.component_key]

        sem = asyncio.Semaphore(1)  # Только 1 ИИ-запрос одновременно (rate limit GigaChat)

        async def bounded(item):
            if PROGRESS_TRACKER.get(report_id, {}).get("cancel", False):
                return None
            async with sem:
                if PROGRESS_TRACKER.get(report_id, {}).get("cancel", False):
                    return None
                res = await fetch_package_info_with_version(
                    session, item["name"], item["version"], cached_rules, report_id, ai_provider,
                    pre_license=item.get("_license"))
                # Пауза 1.5 сек перед следующим ИИ-запросом
                await asyncio.sleep(0.7)
                if report_id in PROGRESS_TRACKER:
                    PROGRESS_TRACKER[report_id]["processed"] += 1
                return res

        async with aiohttp.ClientSession() as session:
            tasks = [bounded(item) for item in items]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            if PROGRESS_TRACKER.get(report_id, {}).get("cancel", False):
                rep = db.query(AuditReport).filter(AuditReport.id == report_id).first()
                if rep:
                    rep.status = "cancelled"
                    db.commit()
                    print(f"[CANCEL] Отчёт #{report_id} помечен как cancelled")
                return
            report_data = [r for r in results if isinstance(r, dict) and r is not None]
            for r in report_data:
                r["category"] = _detect_category(r.get("name", ""))
                r.setdefault("cve_count", 0)
                r.setdefault("cve_list", [])

            # Проверка уязвимостей через OSV
            try:
                vuln_results = await check_osv_vulnerabilities(session, report_data)
                for r in report_data:
                    vulns = vuln_results.get(r.get("name", ""), {})
                    r["cve_count"] = vulns.get("count", 0)
                    r["cve_list"] = vulns.get("vulns", [])
                    if r["cve_count"] > 0 and "❌" not in str(r.get("status", "")):
                        has_critical = any(v.get("severity") in ("CRITICAL", "HIGH") for v in r.get("cve_list", []))
                        if has_critical and "⚠️" not in str(r.get("status", "")):
                            r["status"] = "⚠️ Требует внимания <br><small style='color:#e53e3e;'>🔒 " + str(r["cve_count"]) + " уязвимостей (CRITICAL/HIGH)</small>"
                        else:
                            r["status"] = r["status"] + f" <br><small style='color:#e53e3e;'>🔒 Найдено {r['cve_count']} уязвимостей</small>"
            except Exception as e:
                print(f"[OSV] Ошибка проверки уязвимостей: {e}")

        if not is_pro and total_parsed > FREE_COMPONENTS_LIMIT:
            hidden = total_parsed - FREE_COMPONENTS_LIMIT
            report_data.append({
                "name": f"⚠️ Скрыто ещё {hidden} компонентов",
                "version": "???",
                "license": "🔒 <a href='/pricing' style='color:#3182ce;font-weight:600;'>Перейти на Pro</a>",
                "status": f"⚠️ Ограничено демо-режимом <br><small style='color:#dd6b20;'>💡 Показано {FREE_COMPONENTS_LIMIT} из {total_parsed}. <a href='/pricing' style='color:#3182ce;'>Подключить Pro →</a></small>",
                "category": "Прочее",
                "cve_count": 0,
                "cve_list": [],
            })

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        clean_base = re.sub(r"[^\w\-_\.]", "_", filename.split(".")[0])
        excel_filename = f"audit_{timestamp}_{clean_base}.xlsx"
        await asyncio.to_thread(generate_excel_report, report_data, excel_filename)

        safe_count = sum(1 for i in report_data
                         if "Разрешено" in str(i.get("status", ""))
                         and "⚠️" not in str(i.get("status", ""))
                         and "❌" not in str(i.get("status", "")))
        danger_count = sum(1 for i in report_data if "❌" in str(i.get("status", "")))
        warn_count = len(report_data) - safe_count - danger_count
        cve_total = sum(i.get("cve_count", 0) for i in report_data)
        verdict_data = _build_verdict(report_data)

        rep = db.query(AuditReport).filter(AuditReport.id == report_id).first()
        if rep:
            rep.status = "completed"
            rep.excel_filename = excel_filename
            rep.report_json = json.dumps(report_data)
            rep.verdict_json = json.dumps(verdict_data)
            rep.total_count = total_parsed
            rep.safe_count = safe_count
            rep.warn_count = warn_count
            rep.danger_count = danger_count
            rep.cve_count = cve_total
            db.commit()
    except Exception as e:
        print(f"Audit error: {e}")
        import traceback
        traceback.print_exc()
        rep = db.query(AuditReport).filter(AuditReport.id == report_id).first()
        if rep:
            rep.status = "failed"
            db.commit()
    finally:
        PROGRESS_TRACKER.pop(report_id, None)
        db.close()


async def process_docker_scan_task(report_id: int, image_name: str):
    db = SessionLocal()
    try:
        PROGRESS_TRACKER[report_id] = {"total": 2, "processed": 1, "cancel": False}
        scan = await scan_docker_image(image_name)

        report_data = []
        report_data.append({
            "name": f"🐳 Базовая ОС: {scan['os']}",
            "version": image_name,
            "license": scan["os_status"],
            "status": f"{scan['os_status']} <br><small style='color:#4a5568;'>💡 {scan['os_recommendation']}</small>",
            "category": "Операционные системы",
            "cve_count": 0,
            "cve_list": [],
        })
        for pkg in scan["packages"]:
            status_text = pkg["status"]
            if pkg["recommendation"]:
                status_text += f" <br><small style='color:#4a5568;'>💡 {pkg['recommendation']}</small>"
            report_data.append({
                "name": pkg["name"],
                "version": pkg["version"],
                "license": "—",
                "status": status_text,
                "category": _detect_category(pkg["name"]),
                "cve_count": 0,
                "cve_list": [],
            })

        PROGRESS_TRACKER[report_id]["processed"] = 2

        # Проверка уязвимостей для Docker-пакетов
        try:
            async with aiohttp.ClientSession() as osv_session:
                vuln_results = await check_osv_vulnerabilities(osv_session, report_data)
                for r in report_data:
                    vulns = vuln_results.get(r.get("name", ""), {})
                    r["cve_count"] = vulns.get("count", 0)
                    r["cve_list"] = vulns.get("vulns", [])
                    if r["cve_count"] > 0 and "❌" not in str(r.get("status", "")):
                        r["status"] = r["status"] + f" <br><small style='color:#e53e3e;'>🔒 Найдено {r['cve_count']} уязвимостей</small>"
        except Exception as e:
            print(f"[OSV] Ошибка проверки уязвимостей (Docker): {e}")

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        clean_img = re.sub(r"[^\w\-_.]", "_", image_name)
        excel_filename = f"docker_{timestamp}_{clean_img}.xlsx"
        await asyncio.to_thread(generate_excel_report, report_data, excel_filename)

        safe_count = sum(1 for i in report_data
                         if "Разрешено" in str(i.get("status", ""))
                         and "⚠️" not in str(i.get("status", ""))
                         and "❌" not in str(i.get("status", "")))
        danger_count = sum(1 for i in report_data if "❌" in str(i.get("status", "")))
        warn_count = len(report_data) - safe_count - danger_count
        cve_total = sum(i.get("cve_count", 0) for i in report_data)
        verdict_data = _build_verdict(report_data)

        rep = db.query(AuditReport).filter(AuditReport.id == report_id).first()
        if rep:
            rep.status = "completed"
            rep.excel_filename = excel_filename
            rep.report_json = json.dumps(report_data)
            rep.verdict_json = json.dumps(verdict_data)
            rep.total_count = len(report_data)
            rep.safe_count = safe_count
            rep.warn_count = warn_count
            rep.danger_count = danger_count
            rep.cve_count = cve_total
            db.commit()
    except Exception as e:
        print(f"Docker scan error: {e}")
        import traceback
        traceback.print_exc()
        rep = db.query(AuditReport).filter(AuditReport.id == report_id).first()
        if rep:
            rep.status = "failed"
            db.commit()
    finally:
        PROGRESS_TRACKER.pop(report_id, None)
        db.close()


def generate_excel_report(report_data: list, filename: str) -> str:
    filepath = os.path.join(PDF_DIR, filename)
    try:
        df = pd.DataFrame([{
            "Компонент": re.sub(r"<[^<]+?>", "", str(i.get("name", ""))).strip(),
            "Версия": i.get("version", "unknown"),
            "Категория": i.get("category", "Прочее"),
            "Лицензия": re.sub(r"<[^<]+?>", "", str(i.get("license", ""))),
            "Статус": re.sub(r"<[^<]+?>", "", str(i.get("status", ""))),
            "CVE": ", ".join([v.get("cve", "") for v in i.get("cve_list", [])]) if i.get("cve_count", 0) > 0 else "—",
            "Кол-во уязвимостей": i.get("cve_count", 0),
        } for i in report_data])
        df.to_excel(filepath, index=False, engine="openpyxl")
    except Exception as e:
        print(f"Excel error: {e}")
    return filepath


# ==========================================
# HTML ШАБЛОНЫ
# ==========================================
PDF_DIR = "generated_reports"
os.makedirs(PDF_DIR, exist_ok=True)

FOOTER_HTML = """
<footer style="margin-top: 50px; padding: 25px; text-align: center; color: #4a5568; font-size: 11px; border-top: 1px solid #cbd5e0; background: #edf2f7;">
    <div style="background: #fffaf0; border: 1px solid #fbd38d; color: #744210; padding: 12px 15px; border-radius: 6px; font-size: 12px; margin-bottom: 15px; text-align: left; max-width: 800px; margin-left: auto; margin-right: auto;">
        ⚠️ <b>Сервис находится в режиме бета-тестирования.</b> Возможны ошибки в анализе и временная недоступность. Результаты проверок носят исключительно информационно-справочный характер и не являются официальным юридическим заключением.
    </div>
    <b>Юридическое уведомление:</b> Сервис предоставляет предварительный автоматизированный анализ согласно методическим рекомендациям Минцифры и ПП РФ № 1236. Результаты не являются официальным юридическим заключением или гарантией включения в Реестр.<br>
    <div style="margin-top: 8px;">
        <a href="/terms" style="color:#3182ce;text-decoration:underline;margin: 0 10px;">Пользовательское соглашение</a>
        <a href="/feedback" style="color:#3182ce;text-decoration:underline;margin: 0 10px;">📮 Обратная связь</a>
    </div>
</footer>

<button id="scrollTopBtn" onclick="scrollToTop()" title="Наверх" style="
    display: none;
    position: fixed;
    bottom: 30px;
    right: 30px;
    z-index: 999;
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: #3182ce;
    color: white;
    border: none;
    font-size: 22px;
    cursor: pointer;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    transition: opacity 0.3s, transform 0.3s;
    line-height: 1;
    padding: 0;
">↑</button>

<script>
(function() {
    var btn = document.getElementById('scrollTopBtn');
    if (!btn) return;
    window.addEventListener('scroll', function() {
        if (window.scrollY > 300) {
            btn.style.display = 'block';
            setTimeout(function() { btn.style.opacity = '1'; btn.style.transform = 'translateY(0)'; }, 10);
        } else {
            btn.style.opacity = '0';
            btn.style.transform = 'translateY(20px)';
            setTimeout(function() { btn.style.display = 'none'; }, 300);
        }
    });
    btn.addEventListener('mouseenter', function() { btn.style.background = '#2c5282'; });
    btn.addEventListener('mouseleave', function() { btn.style.background = '#3182ce'; });
})();

function scrollToTop() {
    window.scrollTo({ top: 0, behavior: 'smooth' });
}
</script>
"""

BETA_BANNER_HTML = """
<div style="background: #fffaf0; border-left: 5px solid #dd6b20; padding: 14px 20px; border-radius: 8px; margin-bottom: 20px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
    <span style="font-size: 22px;">🧪</span>
    <div style="flex: 1; min-width: 200px;">
        <b style="color: #c05621; font-size: 14px;">Сервис в режиме бета-тестирования</b>
        <div style="color: #744210; font-size: 12px; margin-top: 2px;">Мы дорабатываем систему. Заметили ошибку или есть идея? <a href="/feedback" style="color: #3182ce; font-weight: 600;">Напишите нам →</a></div>
    </div>
</div>
"""

STATUS_LEGEND_HTML = """
<details style="background: #f8fafc; border: 1px solid #cbd5e0; border-radius: 6px; padding: 14px 18px; margin-bottom: 25px; font-size: 13px; color: #4a5568;">
    <summary style="font-weight: 700; color: #1a365d; cursor: pointer;">ℹ️ Справочник статусов</summary>
    <div style="margin-top: 12px; line-height: 1.6; border-top: 1px dashed #cbd5e0; padding-top: 10px;">
        <p><b style="color:#2f855a;">✅ Разрешено:</b> MIT, Apache-2.0, BSD, российское ПО из Реестра.</p>
        <p><b style="color:#2b6cb0;">ℹ️ Разрешено с условиями:</b> LGPL/MPL (динамическая линковка), Ubuntu.</p>
        <p><b style="color:#dd6b20;">⚠️ Требует внимания:</b> Проприетарные библиотеки, OpenJDK, SSPL/RSALv2, Unity/Unreal.</p>
        <p><b style="color:#e53e3e;">❌ Запрещено:</b> Иностранные ОС, CUDA, Elasticsearch, Google Cloud, AWS.</p>
        <p><b style="color:#e53e3e;">🔒 Уязвимости:</b> Найденные CVE по данным OSV API.</p>
    </div>
</details>
"""

FILE_UPLOAD_HTML = """
<div style="background: linear-gradient(135deg, #f8fafc 0%, #edf2f7 100%); border-radius: 14px; padding: 30px 25px; margin: 25px 0; border: 1px solid #e2e8f0; box-shadow: 0 2px 8px rgba(0,0,0,0.03);">

    <!-- Заголовок -->
    <div style="text-align: center; margin-bottom: 25px;">
        <div style="font-size: 36px; margin-bottom: 6px; line-height: 1;">📂</div>
        <h3 style="color: #1a365d; margin: 0 0 6px 0; font-size: 22px; font-weight: 700;">Загрузите компоненты</h3>
        <p style="color: #718096; margin: 0; font-size: 13px;">Файл, текст или список зависимостей для аудита</p>
    </div>

    <!-- Выбор ИИ -->
    <div style="display: flex; justify-content: center; align-items: center; gap: 10px; margin-bottom: 25px; flex-wrap: wrap;">
        <label style="font-size: 13px; font-weight: 600; color: #4a5568;">🧠 ИИ-анализ:</label>
        <select name="ai_provider" style="padding: 8px 16px; border-radius: 8px; border: 1px solid #cbd5e0; font-size: 13px; background: white; cursor: pointer; color: #2d3748; font-weight: 500;">
            <option value="auto" selected>🔀 Авто (GigaChat → база)</option>
            <option value="gigachat">GigaChat (Сбер)</option>
        </select>
    </div>

    <!-- Два способа: grid -->
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 5px;">

        <!-- Способ 1: Файл -->
        <div style="background: white; border-radius: 12px; padding: 22px 20px; border: 1px solid #e2e8f0; transition: all 0.2s ease;">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 15px;">
                <span style="font-size: 22px;">📎</span>
                <div>
                    <div style="font-size: 15px; font-weight: 700; color: #2d3748;">Способ 1: Файл</div>
                    <div style="font-size: 11px; color: #718096;">Выберите файл с зависимостями</div>
                </div>
            </div>
            <input type="file" name="file" accept=".txt,.xlsx,.xls,.docx,.json" style="width: 100%; font-size: 13px; padding: 10px; border: 2px dashed #cbd5e0; border-radius: 8px; background: #f8fafc; cursor: pointer; box-sizing: border-box;">
            <div style="margin-top: 12px; display: flex; flex-wrap: wrap; gap: 5px;">
                <span style="background: #ebf8ff; color: #2b6cb0; padding: 3px 8px; border-radius: 5px; font-size: 10px; font-family: monospace; font-weight: 600;">.txt</span>
                <span style="background: #ebf8ff; color: #2b6cb0; padding: 3px 8px; border-radius: 5px; font-size: 10px; font-family: monospace; font-weight: 600;">.json</span>
                <span style="background: #ebf8ff; color: #2b6cb0; padding: 3px 8px; border-radius: 5px; font-size: 10px; font-family: monospace; font-weight: 600;">.xlsx</span>
                <span style="background: #ebf8ff; color: #2b6cb0; padding: 3px 8px; border-radius: 5px; font-size: 10px; font-family: monospace; font-weight: 600;">.docx</span>
            </div>
        </div>

        <!-- Способ 2: Текст -->
        <div style="background: white; border-radius: 12px; padding: 22px 20px; border: 1px solid #e2e8f0; transition: all 0.2s ease;">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 15px;">
                <span style="font-size: 22px;">✏️</span>
                <div>
                    <div style="font-size: 15px; font-weight: 700; color: #2d3748;">Способ 2: Текст</div>
                    <div style="font-size: 11px; color: #718096;">Список вида имя==версия</div>
                </div>
            </div>
            <textarea name="text_input" maxlength="500" placeholder="fastapi==0.115.6&#10;pandas==2.2.3&#10;sqlalchemy==2.0.35" style="width: 100%; min-height: 100px; padding: 10px; border: 2px solid #cbd5e0; border-radius: 8px; font-family: 'Courier New', monospace; font-size: 12px; resize: vertical; box-sizing: border-box; background: #f8fafc; line-height: 1.5;"></textarea>
        </div>

    </div>
</div>
"""

GUIDELINES_HTML = """
<div class="card" style="margin-top: 25px; background: #f8fafc; border-top: 4px solid #3182ce; padding: 20px; border-radius: 8px;">
    <h3 style="color: #1a365d; margin-top: 0;">📌 Рекомендации</h3>
    <ul style="font-size: 14px; color: #4a5568; line-height: 1.7;">
        <li><b>SBOM (CycloneDX/SPDX):</b> <code>.cdx.json</code>, <code>.spdx.json</code>, <code>package.json</code></li>
        <li><b>Word:</b> Maven-координаты, списки с тире.</li>
        <li><b>Текстом:</b> по одной строке <code>имя==версия</code></li>
        <li><b>CVE:</b> автоматически проверяется через OSV API (только для компонентов с известной версией).</li>
    </ul>
</div>
"""


METRIKA_ID = "113107006"

METRIKA_SCRIPT = """<!-- Yandex.Metrika counter -->
<script type="text/javascript">
    (function(m,e,t,r,i,k,a){m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
    m[i].l=1*new Date();
    for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
    k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)})
    (window, document, "script", "https://mc.yandex.ru/metrika/tag.js", "ym");

    ym(""" + METRIKA_ID + """, "init", {
        ssr: true,
        webvisor: true,
        clickmap: true,
        ecommerce: "dataLayer",
        accurateTrackBounce: true,
        trackLinks: true
    });
</script>
<noscript><div><img src="https://mc.yandex.ru/watch/""" + METRIKA_ID + """" style="position:absolute; left:-9999px;" alt="" /></div></noscript>
<!-- /Yandex.Metrika counter -->"""


@app.middleware("http")
async def add_metrika(request: Request, call_next):
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type:
        return response
    try:
        # Собираем тело из стримингового ответа
        body_chunks = []
        async for chunk in response.body_iterator:
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8")
            body_chunks.append(chunk)
        body = b"".join(body_chunks).decode("utf-8", errors="ignore")

        # Вставляем метрику перед </head>
        if "</head>" in body and "mc.yandex.ru/metrika" not in body:
            body = body.replace("</head>", METRIKA_SCRIPT + "\n</head>", 1)
            print(f"[METRIKA] Скрипт вставлен в {request.url.path}")

        # Формируем новый ответ
        from starlette.responses import Response as StarletteResponse
        new_headers = {k: v for k, v in response.headers.items()
                       if k.lower() not in ("content-length", "content-type")}
        return StarletteResponse(
            content=body,
            status_code=response.status_code,
            headers=new_headers,
            media_type="text/html",
        )
    except Exception as e:
        print(f"[METRIKA] error: {e}")
        return response


@app.middleware("http")
async def log_visits(request: Request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith(('/download', '/static', '/favicon.ico', '/audit/')):
        db = SessionLocal()
        try:
            ip = request.client.host if request.client else "unknown"
            db.add(VisitLog(path=request.url.path, ip_address=ip))
            db.commit()
        except Exception:
            pass
        finally:
            db.close()
    return response


def _build_nav(user: Optional[User]) -> str:
    feedback_link = "<a href='/feedback' style='color:#3182ce;text-decoration:none;font-weight:600;'>📮 Обратная связь</a>"
    about_link = "<a href='/about' style='color:#3182ce;text-decoration:none;font-weight:600;'>ℹ️ О сервисе</a>"
    if user:
        admin_link = " | <a href='/admin' style='color:#e53e3e;font-weight:700;text-decoration:none;'>Панель администратора</a>" if user.role == "admin" else ""
        return (f"<span style='color:#2d3748;'>👤 <b>{user.email}</b> <span style='color:#718096;font-size:12px;'>({user.role})</span></span>"
                f" | <a href='/dashboard' style='color:#3182ce;text-decoration:none;font-weight:600;'>Личный кабинет</a>"
                f"{admin_link} | <a href='/pricing' style='color:#3182ce;text-decoration:none;font-weight:600;'>Тарифы</a>"
                f" | {feedback_link}"
                f" | {about_link}"
                f" | <a href='/logout' style='color:#718096;text-decoration:none;'>Выйти</a>")
    return ("<a href='/login' style='color:#3182ce;text-decoration:none;font-weight:600;'>Вход</a>"
            " | <a href='/register' style='background:#3182ce;color:white;padding:6px 14px;border-radius:4px;text-decoration:none;font-weight:600;'>Регистрация</a>"
            " | <a href='/pricing' style='color:#3182ce;text-decoration:none;font-weight:600;'>Тарифы</a>"
            f" | {feedback_link}"
            f" | {about_link}")


def _free_plan_banner(user: Optional[User], request: Optional[Request]) -> str:
    if user and user.role == "admin":
        return ""

    if user and user.subscription_plan in ["Pro", "Unlimited"]:
        left = get_free_checks_left(user, request)
        if left <= 5:
            color = "#dd6b20" if left <= 2 else "#3182ce"
            bg = "#fffaf0" if left <= 2 else "#ebf8ff"
            return f"""
            <div style="background: {bg}; border-left: 5px solid {color}; padding: 15px 20px; border-radius: 8px; margin-bottom: 25px;">
                <b style="color: {color}; font-size: 14px;">💎 Pro: осталось {left} из {PRO_CHECKS_LIMIT} проверок в этом месяце</b>
                <div style="color: #4a5568; font-size: 12px; margin-top: 4px;">Лимит автоматически обновится через 30 дней.</div>
            </div>
            """
        return ""

    left = get_free_checks_left(user, request)
    total = FREE_CHECKS_LIMIT

    if left <= 0:
        return f"""
        <div style="background: #fff5f5; border-left: 5px solid #e53e3e; padding: 20px 25px; border-radius: 8px; margin-bottom: 25px;">
            <h3 style="margin: 0 0 8px 0; color: #c53030; font-size: 17px;">⛔ Бесплатные проверки закончились ({total} из {total})</h3>
            <p style="margin: 0 0 15px 0; color: #4a5568; font-size: 13px;">Чтобы продолжить аудит, выберите подходящий тариф:</p>
            <a href="/pricing" style="background: #3182ce; color: white; padding: 10px 20px; border-radius: 4px; text-decoration: none; font-weight: 600; margin-right: 10px;">💎 Pro — от 7 900 ₽/мес</a>
            <a href="/pricing" style="background: #2f855a; color: white; padding: 10px 20px; border-radius: 4px; text-decoration: none; font-weight: 600;">Разовая — 1 900 ₽</a>
        </div>
        """

    color = "#dd6b20" if left <= 2 else "#3182ce"
    bg = "#fffaf0" if left <= 2 else "#ebf8ff"
    return f"""
    <div style="background: {bg}; border-left: 5px solid {color}; padding: 15px 20px; border-radius: 8px; margin-bottom: 25px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
        <div>
            <b style="color: {color}; font-size: 15px;">🆓 Бесплатный план: осталось {left} из {total} проверок</b>
            <div style="color: #4a5568; font-size: 12px; margin-top: 4px;">Отчёты показывают до {FREE_COMPONENTS_LIMIT} компонентов. Для полного доступа — <a href="/pricing" style="color: #3182ce; font-weight: 600;">тариф Pro</a>.</div>
        </div>
    </div>
    """


@app.get("/robots.txt", response_class=HTMLResponse)
async def robots_txt(request: Request):
    base_url = "https://reestr-audit.ru"
    content = f"""User-agent: *
Allow: /
Disallow: /admin
Disallow: /dashboard
Disallow: /audit/
Disallow: /download_excel/
Disallow: /logout
Disallow: /feedback

Sitemap: {base_url}/sitemap.xml
"""
    return HTMLResponse(content=content, media_type="text/plain")


@app.get("/sitemap.xml", response_class=HTMLResponse)
async def sitemap_xml(request: Request):
    base_url = "https://reestr-audit.ru"
    from datetime import datetime as dt
    today = dt.utcnow().strftime("%Y-%m-%d")
    pages = [
        ("", "1.0", "daily"),
        ("about", "0.8", "weekly"),
        ("pricing", "0.9", "weekly"),
        ("terms", "0.3", "monthly"),
        ("feedback", "0.4", "monthly"),
    ]
    items = ""
    for path, prio, freq in pages:
        loc = f"{base_url}/{path}" if path else f"{base_url}/"
        items += f"""  <url>
    <loc>{loc}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{freq}</changefreq>
    <priority>{prio}</priority>
  </url>
"""
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{items}</urlset>
"""
    return HTMLResponse(content=xml, media_type="application/xml")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "component-expert", "version": APP_VERSION}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(get_current_user)):
    if user and user.role == "admin" and user.subscription_plan not in ["Pro", "Unlimited"]:
        user.subscription_plan = "Pro"

    free_left = get_free_checks_left(user, request)
    limit_reached = free_left <= 0 and not (user and (user.role == "admin" or user.subscription_plan in ["Pro", "Unlimited"]))

    banner_html = _free_plan_banner(user, request)

    if limit_reached:
        form_html = f"""
        <div style="text-align:center; padding: 40px 20px;">
            <h2 style="color: #e53e3e; margin-top: 0;">⛔ Бесплатные проверки закончились</h2>
            <p style="color: #4a5568; margin-bottom: 25px;">Вы использовали все {FREE_CHECKS_LIMIT} бесплатных проверок. Чтобы продолжить аудит, выберите тариф:</p>
            <a href="/pricing" style="display:inline-block; background:#3182ce; color:white; padding: 14px 28px; border-radius: 6px; text-decoration: none; font-weight: 600; font-size: 15px;">💎 Посмотреть тарифы</a>
        </div>
        """
    else:
        form_html = f"""
        <form action="/upload" method="post" enctype="multipart/form-data">
            {FILE_UPLOAD_HTML}
            <button type="submit" class="submit-btn">🚀 Запустить аудит</button>
        </form>
        """

    return HTMLResponse(content=f"""
    <!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Компонент-Эксперт — автоматизированный аудит ПО по ПП РФ № 1236</title>
    <meta name="description" content="Сервис автоматизированного аудита программного обеспечения на соответствие Постановлению Правительства РФ № 1236. Проверка лицензий, CVE-уязвимостей, запрещённых компонентов за минуты.">
    <meta name="keywords" content="аудит ПО, ПП 1236, реестр российского ПО, проверка лицензий, CVE, импортозамещение, экспертиза ПО">
    <meta name="author" content="Захаров Николай Петрович">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://reestr-audit.ru/">
    <meta property="og:title" content="Компонент-Эксперт — аудит ПО по ПП 1236">
    <meta property="og:description" content="Проверьте своё ПО на соответствие требованиям Единого реестра российского ПО за минуты.">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://reestr-audit.ru/">
    <meta property="og:site_name" content="Компонент-Эксперт">
    <meta name="twitter:card" content="summary">
    <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%F0%9F%9B%A1%EF%B8%8F%3C/text%3E%3C/svg%3E">
    <style>
        body {{ font-family: -apple-system, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #f7fafc; color: #2d3748; }}
        @media (max-width: 640px) {{
            div[style*="grid-template-columns: 1fr 1fr"] {{ grid-template-columns: 1fr !important; }}
        }}
        .nav {{ display: flex; justify-content: space-between; padding: 15px 0; border-bottom: 1px solid #e2e8f0; margin-bottom: 30px; font-size: 14px; align-items: center; flex-wrap: wrap; gap: 10px; }}
        .nav-brand {{ font-weight: 800; color: #1a365d; font-size: 16px; }}
        .card {{ background: white; padding: 40px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border-top: 4px solid #1a365d; }}
        h1 {{ color: #1a365d; text-align: center; }}
        .submit-btn {{ background: linear-gradient(135deg, #38a169 0%, #2f855a 100%); color: white; border: none; padding: 16px 32px; font-size: 16px; font-weight: 700; border-radius: 10px; cursor: pointer; width: 100%; margin-top: 20px; box-shadow: 0 4px 12px rgba(47,133,90,0.25); transition: all 0.2s ease; letter-spacing: 0.3px; }}
        .submit-btn:hover {{ background: linear-gradient(135deg, #2f855a 0%, #276749 100%); box-shadow: 0 6px 16px rgba(47,133,90,0.35); transform: translateY(-1px); }}
        .submit-btn:active {{ transform: translateY(0); box-shadow: 0 2px 6px rgba(47,133,90,0.25); }}
    </style></head><body>
    <div class="nav"><div class="nav-brand">🛡️ Компонент-Эксперт</div><div>{_build_nav(user)}</div></div>
    <div class="card">
        <h1>Платформа «Компонент-Эксперт»</h1>
        <p style="text-align: center; color: #4a5568; margin-bottom: 20px;">Автоматизированный аудит ПО на соответствие ПП РФ № 1236</p>
        {BETA_BANNER_HTML}
        {banner_html}
        {form_html}
    </div>
    {GUIDELINES_HTML}
    {FOOTER_HTML}
    </body></html>
    """)


@app.post("/upload")
async def upload_file(
    request: Request,
    background_tasks: BackgroundTasks,
    file: Optional[UploadFile] = File(None),
    text_input: Optional[str] = Form(None),
    docker_image: Optional[str] = Form(None),
    ai_provider: str = Form("auto"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # --- RATE LIMITING ---
    allowed, remaining, retry_after = check_rate_limit(request, "/upload", user)
    if not allowed:
        return HTMLResponse(
            f"""<html><head><meta charset="UTF-8"><title>429 — Слишком много запросов</title>
            <style>body{{font-family:sans-serif;text-align:center;padding:60px;background:#f7fafc;}}
            .card{{background:white;max-width:520px;margin:0 auto;padding:40px;border-radius:8px;
            border-top:5px solid #e53e3e;box-shadow:0 4px 12px rgba(0,0,0,0.05);}}
            h1{{color:#e53e3e;}} p{{color:#4a5568;line-height:1.6;}}</style></head><body>
            <div class="card">
              <h1>⏱ Слишком много запросов</h1>
              <p>Вы превысили лимит: <b>{RATE_LIMIT_GUEST} проверок в минуту</b> для бесплатного плана.</p>
              <p>Подождите <b>{retry_after} секунд</b> и попробуйте снова.</p>
              <p style="font-size:13px;">Для увеличения лимита перейдите на тариф Pro
              (30 проверок в минуту).</p>
              <p><a href="/pricing" style="color:#3182ce;font-weight:600;">Посмотреть тарифы →</a></p>
              <p><a href="/" style="color:#718096;">← Вернуться на главную</a></p>
            </div>
            </body></html>""",
            status_code=429,
            headers={"Retry-After": str(retry_after)}
        )
    # --- /RATE LIMITING ---

    # --- RATE LIMITING ---
    # --- /RATE LIMITING ---

    free_left = get_free_checks_left(user, request)
    unlimited = is_unlimited(user)

    if not unlimited and free_left <= 0:
        return RedirectResponse(url="/pricing", status_code=status.HTTP_303_SEE_OTHER)

    is_pro = unlimited

    # Отклоняем PDF с понятным сообщением
    if file and file.filename and file.filename.lower().endswith(".pdf"):
        return HTMLResponse(
            """<html><head><meta charset="UTF-8"><title>Формат не поддерживается</title>
            <style>body{font-family:sans-serif;text-align:center;padding:60px;background:#f7fafc;}
            .card{background:white;max-width:520px;margin:0 auto;padding:40px;border-radius:8px;
            border-top:5px solid #dd6b20;box-shadow:0 4px 12px rgba(0,0,0,0.05);}
            h1{color:#dd6b20;} p{color:#4a5568;line-height:1.6;}</style></head><body>
            <div class="card">
              <h1>📄 PDF временно не поддерживается</h1>
              <p>Извлечение компонентов из PDF даёт много ложных срабатываний.</p>
              <p>Пожалуйста, загрузите файл в одном из форматов:</p>
              <p style="font-family:monospace;background:#edf2f7;padding:10px;border-radius:4px;">
              .txt · .json · .xlsx · .docx</p>
              <p><a href="/" style="color:#3182ce;font-weight:600;">← Вернуться на главную</a></p>
            </div>
            </body></html>""",
            status_code=400,
        )

    if not unlimited and user:
        if user.subscription_plan in ["Pro", "Unlimited"]:
            user.pro_checks_used = (user.pro_checks_used or 0) + 1
        else:
            user.free_checks_used = (user.free_checks_used or 0) + 1
        db.commit()

    if docker_image and docker_image.strip():
        new_report = AuditReport(user_id=user.id if user else None,
                                 filename=f"docker:{docker_image.strip()}", status="pending")
        db.add(new_report)
        db.commit()
        db.refresh(new_report)
        background_tasks.add_task(process_docker_scan_task, new_report.id, docker_image.strip())
        response = RedirectResponse(url=f"/audit/{new_report.id}/progress", status_code=status.HTTP_303_SEE_OTHER)
        if not user:
            gc = int(request.cookies.get("guest_audit_count", 0))
            response.set_cookie(key="guest_audit_count", value=str(gc + 1), max_age=2592000, httponly=True, secure=COOKIE_SECURE, samesite="lax")
        return response

    file_bytes = b""
    filename = "manual_input.txt"
    if file and file.filename:
        file_bytes = await file.read()
        filename = file.filename
    elif text_input and text_input.strip():
        file_bytes = text_input.encode("utf-8")
    else:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

    new_report = AuditReport(user_id=user.id if user else None, filename=filename, status="pending")
    db.add(new_report)
    db.commit()
    db.refresh(new_report)
    background_tasks.add_task(process_audit_task, new_report.id, file_bytes, filename, is_pro, ai_provider)

    response = RedirectResponse(url=f"/audit/{new_report.id}/progress", status_code=status.HTTP_303_SEE_OTHER)
    if not user:
        gc = int(request.cookies.get("guest_audit_count", 0))
        response.set_cookie(key="guest_audit_count", value=str(gc + 1), max_age=2592000, httponly=True, secure=COOKIE_SECURE, samesite="lax")
    return response


@app.get("/register", response_class=HTMLResponse)
async def register_page():
    return HTMLResponse(content="""
    <div style='max-width:460px;margin:60px auto;padding:35px;background:white;border-radius:8px;border-top:4px solid #1a365d;font-family:sans-serif;'>
    <h2 style="margin-top:0;">Регистрация</h2>
    <p style="color:#718096;font-size:13px;line-height:1.5;">При регистрации вы получаете <b>5 бесплатных проверок</b>. Отчёты показывают до 10 компонентов. Для полного доступа доступны тарифы.</p>
    <form action="/register" method="post">
        <label style="font-size:13px;font-weight:600;display:block;margin-top:15px;">Организация</label>
        <input type="text" name="company_name" required style="width:100%;padding:10px;margin:5px 0;box-sizing:border-box;border:1px solid #cbd5e0;border-radius:4px;">
        <label style="font-size:13px;font-weight:600;display:block;margin-top:15px;">Email</label>
        <input type="email" name="email" required style="width:100%;padding:10px;margin:5px 0;box-sizing:border-box;border:1px solid #cbd5e0;border-radius:4px;">
        <label style="font-size:13px;font-weight:600;display:block;margin-top:15px;">Пароль</label>
        <input type="password" name="password" required style="width:100%;padding:10px;margin:5px 0;box-sizing:border-box;border:1px solid #cbd5e0;border-radius:4px;">
        <div style="display:flex;align-items:flex-start;gap:10px;margin-top:18px;font-size:12px;color:#4a5568;line-height:1.5;">
            <input type="checkbox" name="terms_accepted" required id="terms" style="margin-top:3px;">
            <label for="terms" style="font-weight:normal;">Я принимаю <a href="/terms" target="_blank" style="color:#3182ce;">Пользовательское соглашение</a>, согласен на обработку персональных данных и ознакомлен с тем, что сервис работает в режиме <b>бета-тестирования</b>.</label>
        </div>
        <button type="submit" style="background:#2f855a;color:white;padding:12px;width:100%;border:none;border-radius:4px;margin-top:20px;cursor:pointer;font-weight:600;">Зарегистрироваться</button>
    </form>
    <p style="text-align:center;margin-top:20px;"><a href="/" style="color:#3182ce;">На главную</a></p></div>
    """)


@app.post("/register")
async def register(request: Request, company_name: str = Form(...), email: str = Form(...), password: str = Form(...),
                   terms_accepted: str = Form(None), db: Session = Depends(get_db)):
    # --- RATE LIMITING ---
    allowed, _, retry_after = check_rate_limit(request, "/register")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Слишком много попыток регистрации. Подождите {retry_after} секунд.",
            headers={"Retry-After": str(retry_after)}
        )
    # --- /RATE LIMITING ---
    if not terms_accepted:
        raise HTTPException(status_code=400, detail="Необходимо принять условия пользовательского соглашения")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email занят")
    assigned_role = "admin" if db.query(User).count() == 0 else "user"
    is_test_user = _is_test_email(email)
    db.add(User(company_name=company_name, email=email, hashed_password=hash_password(password),
                role=assigned_role, subscription_plan="Pro" if assigned_role == "admin" else "Free",
                free_checks_used=0, is_test=is_test_user))
    db.commit()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    return HTMLResponse(content="""
    <div style='max-width:420px;margin:80px auto;padding:35px;background:white;border-radius:8px;border-top:4px solid #1a365d;font-family:sans-serif;'>
    <h2 style="margin-top:0;">Вход</h2>
    <form action="/login" method="post">
        <label style="font-size:13px;font-weight:600;display:block;margin-top:15px;">Email</label>
        <input type="email" name="email" required style="width:100%;padding:10px;margin:5px 0;box-sizing:border-box;border:1px solid #cbd5e0;border-radius:4px;">
        <label style="font-size:13px;font-weight:600;display:block;margin-top:15px;">Пароль</label>
        <input type="password" name="password" required style="width:100%;padding:10px;margin:5px 0;box-sizing:border-box;border:1px solid #cbd5e0;border-radius:4px;">
        <button type="submit" style="background:#3182ce;color:white;padding:12px;width:100%;border:none;border-radius:4px;margin-top:20px;cursor:pointer;font-weight:600;">Войти</button>
    </form>
    <p style="text-align:center;margin-top:20px;"><a href="/" style="color:#3182ce;">На главную</a></p></div>
    """)


@app.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if user.subscription_status == "Blocked":
        return HTMLResponse("<h2 style='text-align:center;color:red;font-family:sans-serif;margin-top:100px;'>Аккаунт заблокирован</h2>", status_code=403)
    token = secrets.token_urlsafe(32)
    user.session_token = token
    db.commit()
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="session_token", value=token, httponly=True, secure=COOKIE_SECURE, samesite="lax")
    return response


@app.get("/logout")
async def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user:
        user.session_token = None
        db.commit()
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="session_token", secure=COOKIE_SECURE, samesite="lax")
    return response


@app.get("/terms", response_class=HTMLResponse)
async def terms_page():
    return HTMLResponse(content="""
    <!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Пользовательское соглашение</title>
    <style>body{font-family:-apple-system,sans-serif;max-width:800px;margin:40px auto;padding:20px;background:#f7fafc;color:#2d3748;line-height:1.7;}
    .card{background:white;padding:40px;border-radius:8px;border-top:4px solid #1a365d;box-shadow:0 4px 6px rgba(0,0,0,0.05);}
    h1,h2{color:#1a365d;} p,li{font-size:14px;}</style></head><body>
    <div class="card">
    <h1>Пользовательское соглашение и юридический дисклеймер</h1>
    <p>Настоящий документ определяет условия использования сервиса «Компонент-Эксперт» (далее — Сервис) и устанавливает объём ответственности сторон.</p>

    <h2>1. Статус сервиса (бета-тестирование)</h2>
    <p>1.1. Сервис находится в режиме <b>бета-тестирования</b>. Это означает, что функциональность может изменяться, возможны ошибки и периоды временной недоступности.</p>
    <p>1.2. Администрация не гарантирует непрерывную работу Сервиса и оставляет за собой право в любой момент изменять, приостанавливать или прекращать его работу без предварительного уведомления.</p>

    <h2>2. Правовой характер информации</h2>
    <p>2.1. Сервис предоставляет автоматизированный экспресс-анализ списков зависимостей ПО на основе открытых реестров и методических рекомендаций Минцифры России.</p>
    <p>2.2. Результаты проверки носят <b>исключительно информационно-консультационный характер</b> и не являются официальным юридическим заключением, аудитом или государственной экспертизой.</p>
    <p>2.3. Использование Сервиса не гарантирует включение ПО в Единый реестр российских программ (ПП РФ № 1236). Окончательное решение принимает Экспертный совет Минцифры РФ.</p>
    <p>2.4. Администрация не несёт ответственности за прямой или косвенный ущерб, убытки, упущенную выгоду или отказ уполномоченных органов, возникшие в результате использования результатов Сервиса.</p>

    <h2>3. Обработка персональных данных</h2>
    <p>3.1. Загружаемые файлы манифестов обрабатываются автоматически в памяти Сервиса с целью формирования аналитического отчёта.</p>
    <p>3.2. Сервис не передаёт загруженные документы третьим лицам.</p>
    <p>3.3. При обращении к внешним ИИ-провайдерам (GigaChat) передаётся только название компонента, без содержимого файла.</p>
    <p>3.4. При регистрации пользователь даёт согласие на обработку персональных данных (email, название организации) в целях предоставления доступа к Сервису.</p>

    <h2>4. Тарифы и лимиты</h2>
    <p>4.1. Бесплатный план включает 5 проверок и отчёты до 10 компонентов.</p>
    <p>4.2. Для получения полного доступа доступны тарифы «Разовая проверка» и «Профессиональный».</p>

    <h2>5. Обратная связь</h2>
    <p>5.1. Пользователь может отправить обращение через форму <a href="/feedback">Обратной связи</a>. Администрация старается отвечать в течение 2 рабочих дней.</p>

    <h2>6. Ограничения</h2>
    <p>6.1. Пользователь обязуется не использовать Сервис для массовых автоматизированных запросов, попыток взлома, распространения вредоносного кода или иных действий, нарушающих законодательство РФ.</p>

    <p style="margin-top:30px;"><a href="/" style="color:#3182ce;text-decoration:none;font-weight:600;">← На главную</a></p>
    </div></body></html>
    """)


@app.get("/feedback", response_class=HTMLResponse)
async def feedback_page(user: User = Depends(get_current_user)):
    return HTMLResponse(content=f"""
    <!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Обратная связь</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f7fafc; color: #2d3748; }}
        .nav {{ display: flex; justify-content: space-between; padding: 15px 0; border-bottom: 1px solid #e2e8f0; margin-bottom: 30px; font-size: 14px; flex-wrap: wrap; gap: 10px; }}
        .nav-brand {{ font-weight: 800; color: #1a365d; font-size: 16px; }}
        .card {{ background: white; padding: 40px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border-top: 4px solid #1a365d; }}
        h1 {{ color: #1a365d; }}
        label {{ font-size: 13px; font-weight: 600; color: #4a5568; display: block; margin-top: 18px; }}
        input, textarea, select {{ width: 100%; padding: 10px 12px; margin-top: 5px; box-sizing: border-box; border: 1px solid #cbd5e0; border-radius: 4px; font-size: 14px; font-family: inherit; }}
        textarea {{ min-height: 140px; resize: vertical; }}
        button {{ background: #2f855a; color: white; border: none; padding: 14px; width: 100%; border-radius: 4px; cursor: pointer; font-size: 15px; font-weight: 600; margin-top: 22px; }}
        button:hover {{ background: #276749; }}
    </style></head><body>
    <div class="nav"><div class="nav-brand">🛡️ Компонент-Эксперт</div><div>{_build_nav(user)}</div></div>

    <div class="card">
        <h1 style="margin-top:0;">📮 Обратная связь</h1>
        <p style="color:#4a5568;font-size:14px;">Сервис работает в режиме <b>бета-тестирования</b>. Если вы нашли ошибку, у вас есть идея по улучшению или вопрос — напишите нам. Мы читаем каждое сообщение.</p>

        <form action="/feedback" method="post">
           <label>Ваше имя *</label>
<input type="text" name="name" required placeholder="Иван Иванов">

            <label>Email для ответа *</label>
           <
           
                      <input type="email" name="email" required value="{user.email if user else ''}" placeholder="user@example.ru">

            <label>Тема обращения</label>
            <select name="subject">
                <option value="Ошибка / Баг">🐛 Ошибка / Баг</option>
                <option value="Предложение по улучшению">💡 Предложение по улучшению</option>
                <option value="Вопрос по функционалу">❓ Вопрос по функционалу</option>
                <option value="Вопрос по тарифам">💰 Вопрос по тарифам</option>
                <option value="Сотрудничество">🤝 Сотрудничество</option>
                <option value="Другое">📝 Другое</option>
            </select>

            <label>Сообщение *</label>
            <textarea name="message" required placeholder="Опишите проблему или предложение как можно подробнее..." minlength="10"></textarea>

            <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px 15px; margin-top: 18px; font-size: 12px; color: #4a5568;">
                Отправляя форму, вы соглашаетесь с <a href="/terms" style="color:#3182ce;">Пользовательским соглашением</a> и обработкой персональных данных.
            </div>

            <button type="submit">Отправить сообщение</button>
        </form>

        <p style="text-align:center; margin-top: 25px;"><a href="/" style="color:#3182ce; text-decoration:none; font-weight:600;">← На главную</a></p>
    </div>

    {FOOTER_HTML}
    </body></html>
    """)


@app.post("/feedback")
async def feedback_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    subject: str = Form("Другое"),
    message: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # --- RATE LIMITING ---
    allowed, _, retry_after = check_rate_limit(request, "/feedback")
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Слишком много обращений. Подождите {retry_after} секунд.",
            headers={"Retry-After": str(retry_after)}
        )
    # --- /RATE LIMITING ---
    try:
        db.add(Feedback(
            name=name.strip()[:200],
            email=email.strip()[:200],
            subject=subject.strip()[:200],
            message=message.strip()[:5000],
            page_url=str(request.headers.get("referer", "/"))[:500],
        ))
        db.commit()
    except Exception as e:
        print(f"Feedback save error: {e}")
        db.rollback()

    return HTMLResponse(content=f"""
    <!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Спасибо!</title>
    <style>body{{font-family:-apple-system,sans-serif;max-width:600px;margin:80px auto;padding:20px;text-align:center;background:#f7fafc;}}
    .card{{background:white;padding:50px;border-radius:8px;border-top:4px solid #2f855a;box-shadow:0 4px 15px rgba(0,0,0,0.05);}}
    h1{{color:#2f855a;}}</style></head><body>
    <div class="card">
        <div style="font-size: 60px; margin-bottom: 20px;">✅</div>
        <h1>Спасибо за обращение!</h1>
        <p style="color:#4a5568;">Мы получили ваше сообщение и постараемся ответить в течение 2 рабочих дней.</p>
        <p style="color:#4a5568;">Ваш вклад помогает нам делать сервис лучше.</p>
        <div style="margin-top: 30px;">
            <a href="/" style="display: inline-block; background: #3182ce; color: white; padding: 12px 28px; border-radius: 6px; text-decoration: none; font-weight: 600;">← На главную</a>
        </div>
    </div>
    </body></html>
    """)


@app.get("/pricing", response_class=HTMLResponse)
async def pricing_page(user: User = Depends(get_current_user)):
    return HTMLResponse(content=f"""
    <!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
    <title>Тарифы — Компонент-Эксперт</title>
    <meta name="description" content="Тарифные планы сервиса «Компонент-Эксперт»: бесплатно, разовая проверка 1 900 ₽, Pro 7 900 ₽/мес (50 проверок), корпоративный план.">
    <link rel="canonical" href="https://reestr-audit.ru/pricing">
    <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%F0%9F%9B%A1%EF%B8%8F%3C/text%3E%3C/svg%3E">
    <style>body{{font-family:-apple-system,sans-serif;max-width:1100px;margin:0 auto;padding:20px;background:#f7fafc;color:#2d3748;}}
    .nav{{display:flex;justify-content:space-between;padding:15px 0;border-bottom:1px solid #e2e8f0;margin-bottom:30px;font-size:14px;flex-wrap:wrap;gap:10px;}}
    .nav-brand{{font-weight:800;color:#1a365d;font-size:16px;}}
    .grid{{display:flex;gap:20px;flex-wrap:wrap;justify-content:center;margin-top:30px;}}
    .card{{background:#f8fafc;border:1px solid #cbd5e0;border-radius:8px;padding:25px;width:250px;display:flex;flex-direction:column;justify-content:space-between;}}
    .card.f{{border-color:#3182ce;border-width:2px;background:#fff;box-shadow:0 10px 15px -3px rgba(0,0,0,0.1);}}
    .pt{{font-size:18px;font-weight:bold;color:#1a365d;margin-bottom:10px;}}
    .pa{{font-size:24px;font-weight:bold;color:#2f855a;margin-bottom:20px;}}
    .pf{{list-style:none;padding:0;margin:0 0 25px 0;font-size:13px;color:#4a5568;}}
    .pf li{{margin-bottom:10px;}}
    .btn{{display:block;text-align:center;background:#3182ce;color:white;padding:10px;border-radius:6px;text-decoration:none;font-weight:600;font-size:14px;border:none;cursor:pointer;}}
    .btn-free{{background:#718096;}} .btn-dev{{background:#cbd5e0;color:#718096;cursor:not-allowed;}}
    </style></head><body>
    <div class="nav"><div class="nav-brand">🛡️ Компонент-Эксперт</div><div>{_build_nav(user)}</div></div>
    <h1 style="text-align:center;color:#1a365d;">Тарифные планы</h1>
    <p style="text-align:center;color:#718096;">Бесплатный план: {FREE_CHECKS_LIMIT} проверок, до {FREE_COMPONENTS_LIMIT} компонентов в отчёте</p>
    <div class="grid">
        <div class="card">
            <div><div class="pt">Старт / Демо</div><div class="pa">Бесплатно</div>
            <ul class="pf"><li>✔️ {FREE_CHECKS_LIMIT} проверок всего</li><li>✔️ До {FREE_COMPONENTS_LIMIT} компонентов</li><li>❌ Без Excel-отчёта</li></ul></div>
            <a href="/register" class="btn btn-free">Начать бесплатно</a>
        </div>
        <div class="card">
            <div><div class="pt">Разовая проверка</div><div class="pa">1 900 ₽</div>
            <ul class="pf"><li>✔️ 1 полная проверка</li><li>✔️ Без лимита компонентов</li><li>✔️ Excel-отчёт</li></ul></div>
            <a href="/register" class="btn" style="background:#2f855a;">Купить</a>
        </div>
        <div class="card f">
            <div><div class="pt">Профессиональный 💎</div><div class="pa">7 900 ₽ <span style="font-size:13px;color:#718096;font-weight:normal;">/мес</span></div>
            <ul class="pf"><li>✔️ {PRO_CHECKS_LIMIT} проверок в месяц</li><li>✔️ Excel-отчёты</li><li>✔️ Проверка CVE</li><li>✔️ Приоритетная поддержка</li></ul></div>
            <form action="/upgrade-to-pro" method="post"><button type="submit" class="btn">Подключить Pro</button></form>
        </div>
        <div class="card" style="opacity:0.85;">
            <div><div class="pt">Корпоративный 🏢</div><div class="pa" style="font-size:18px;color:#d69e2e;">В разработке ⏳</div>
            <ul class="pf"><li>✔️ Безлимит</li><li>✔️ Персональный менеджер</li><li>✔️ API-интеграция</li><li>✔️ On-Premise</li></ul></div>
            <button type="button" class="btn btn-dev" disabled>Скоро</button>
        </div>
    </div>
    <div style="margin-top:40px;text-align:center;"><a href="/" style="color:#3182ce;text-decoration:none;font-weight:600;">← На главную</a></div>
    {FOOTER_HTML}</body></html>
    """)


@app.post("/upgrade-to-pro")
async def upgrade_to_pro(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user:
        user.subscription_plan = "Pro"
        db.commit()
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        return RedirectResponse(url="/login")

    reports = db.query(AuditReport).filter(AuditReport.user_id == user.id).order_by(AuditReport.created_at.desc()).all()
    rows = "".join([
        f"<tr><td style='padding:12px;border-bottom:1px solid #e2e8f0;'><a href='/audit/{r.id}/result'>{r.filename}</a></td>"
        f"<td style='padding:12px;border-bottom:1px solid #e2e8f0;'>{r.created_at.strftime('%Y-%m-%d %H:%M')}</td>"
        f"<td style='padding:12px;border-bottom:1px solid #e2e8f0;'><a href='/download_excel/{r.excel_filename}'>Excel</a></td>"
        f"<td style='padding:12px;border-bottom:1px solid #e2e8f0;'><form method='POST' action='/reports/delete/{r.id}' style='margin:0;'><button type='submit' style='background:none;border:none;color:#e53e3e;cursor:pointer;'>Удалить</button></form></td></tr>"
        for r in reports if r.status == "completed"
    ])

    if user.role == "admin":
        plan_badge = "👑 Администратор (безлимит)"
    elif user.subscription_plan in ["Pro", "Unlimited"]:
        used_pro = user.pro_checks_used or 0
        left_pro = max(0, PRO_CHECKS_LIMIT - used_pro)
        plan_badge = f"💎 Pro (использовано {used_pro} из {PRO_CHECKS_LIMIT}, осталось {left_pro})"
    else:
        used = user.free_checks_used or 0
        left = max(0, FREE_CHECKS_LIMIT - used)
        plan_badge = f"🏷️ Free (использовано {used} из {FREE_CHECKS_LIMIT}, осталось {left})"

    return HTMLResponse(content=f"""
    <!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Личный кабинет</title>
    <style>body{{font-family:sans-serif;max-width:950px;margin:0 auto;padding:20px;background:#f7fafc;}}
    .nav{{display:flex;justify-content:space-between;padding:15px 0;border-bottom:1px solid #e2e8f0;margin-bottom:30px;font-size:14px;flex-wrap:wrap;gap:10px;}}
    .nav-brand{{font-weight:800;color:#1a365d;font-size:16px;}}
    .card{{background:white;padding:35px;border-radius:8px;box-shadow:0 4px 6px rgba(0,0,0,0.05);border-top:4px solid #1a365d;}}
    table{{width:100%;border-collapse:collapse;}} th{{background:#1a365d;color:white;padding:12px;text-align:left;}}</style>
    </head><body>
    <div class="nav"><div class="nav-brand">🛡️ Компонент-Эксперт</div><div>{_build_nav(user)}</div></div>
    <div class="card">
    <h2 style="margin-top:0;">Личный кабинет</h2>
    <p><b>Организация:</b> {user.company_name} | <b>Email:</b> {user.email}</p>
    <p><b>Текущий план:</b> <span style="color:#2b6cb0;font-weight:bold;">{plan_badge}</span></p>
    {BETA_BANNER_HTML}
    {_free_plan_banner(user, None) if user.role != 'admin' and user.subscription_plan not in ['Pro', 'Unlimited'] else ''}
    <form action="/upload" method="post" enctype="multipart/form-data">
        {FILE_UPLOAD_HTML}
        <button type="submit" style="background:#2f855a;color:white;padding:12px 32px;border:none;border-radius:4px;cursor:pointer;margin-top:10px;font-weight:600;">🚀 Загрузить и проверить</button>
    </form>
    <h3 style="margin-top:30px;">Архив проверок</h3>
    <table><tr><th>Файл</th><th>Дата</th><th>Excel</th><th>Действие</th></tr>{rows if rows else "<tr><td colspan='4' style='padding:20px;text-align:center;'>История пуста</td></tr>"}</table>
    </div>{FOOTER_HTML}</body></html>
    """)


@app.post("/reports/delete/{report_id}")
async def delete_report(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user:
        raise HTTPException(status_code=403)
    report = db.query(AuditReport).filter(AuditReport.id == report_id).first()
    if report and (report.user_id == user.id or user.role == "admin"):
        if report.excel_filename:
            fp = os.path.join(PDF_DIR, report.excel_filename)
            if os.path.exists(fp):
                try: os.remove(fp)
                except: pass
        db.delete(report)
        db.commit()
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/audit/{report_id}/progress", response_class=HTMLResponse)
async def audit_progress_page(report_id: int):
    return HTMLResponse(content=f"""
    <!DOCTYPE html><html><head><meta charset="UTF-8"><title>Анализ...</title>
    <style>
        body{{font-family:-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f7fafc;}}
        .card{{background:white;padding:45px;border-radius:8px;border-top:5px solid #3182ce;text-align:center;max-width:520px;box-shadow:0 4px 12px rgba(0,0,0,0.05);}}
        .cancel-btn{{background:#e53e3e;color:white;border:none;padding:10px 24px;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer;margin-top:25px;transition:background 0.2s;}}
        .cancel-btn:hover{{background:#c53030;}}
        .cancel-btn:disabled{{background:#cbd5e0;cursor:not-allowed;}}
    </style>
    </head><body><div class="card">
    <h2 style="color:#1a365d;margin-top:0;">Идёт анализ ПО</h2>
    <p style="color:#4a5568;">ИИ-агент проверяет зависимости и уязвимости...</p>
    <div style="width:100%;background:#e2e8f0;border-radius:4px;height:8px;margin-top:25px;">
        <div id="pf" style="width:0%;height:100%;background:#3182ce;transition:width 0.4s;"></div>
    </div>
    <p id="pt" style="font-size:13px;color:#4a5568;">Подготовка...</p>
    <button class="cancel-btn" id="cancelBtn" onclick="cancelAudit()">⛔ Отменить проверку</button>
    <p id="ct" style="font-size:12px;color:#718096;margin-top:10px;display:none;">Отмена...</p>
    </div>
    <script>
    let cancelled = false;
    let startTime = null;
    let lastProcessed = 0;
    let eta = null;

    function formatTime(sec){{
        if(sec < 60) return Math.round(sec) + ' сек';
        const m = Math.floor(sec / 60);
        const s = Math.round(sec % 60);
        return m + ' мин ' + s + ' сек';
    }}

    function computeEta(processed, total){{
        if(!startTime || processed < 3) return null;
        const elapsed = (Date.now() - startTime) / 1000;
        const speed = processed / elapsed;  // компонентов/сек
        const remaining = total - processed;
        if(speed <= 0) return null;
        return remaining / speed;
    }}

    async function cancelAudit(){{
        if(cancelled) return;
        if(!confirm('Отменить проверку? Все результаты будут удалены.')) return;
        cancelled = true;
        document.getElementById('cancelBtn').disabled = true;
        document.getElementById('cancelBtn').innerText = '⏳ Отмена...';
        document.getElementById('ct').style.display = 'block';
        try {{
            await fetch('/audit/{report_id}/cancel', {{method:'POST'}});
        }} catch(e) {{ console.error(e); }}
        setTimeout(() => {{ window.location.href = '/'; }}, 1500);
    }}

    async function check(){{
        if(cancelled) return;
        try{{
            const r = await fetch('/audit/{report_id}/status');
            const d = await r.json();
            if(d.total>0){{
                if(startTime === null) startTime = Date.now();
                const pct = Math.round((d.processed/d.total)*100);
                document.getElementById('pf').style.width = pct + '%';

                // Пересчитываем ETA каждые 5 компонентов
                if(d.processed > lastProcessed){{
                    eta = computeEta(d.processed, d.total);
                    lastProcessed = d.processed;
                }}

                let text = `Анализ: ${{d.processed}}/${{d.total}} (${{pct}}%)`;
                if(eta !== null && d.processed < d.total){{
                    text += ` — осталось ~${{formatTime(eta)}}`;
                }}
                document.getElementById('pt').innerText = text;
            }}
            if(d.status==='completed') window.location.href='/audit/{report_id}/result';
            else if(d.status==='failed'){{alert('Ошибка анализа');window.location.href='/';}}
            else if(d.status==='cancelled' || d.status==='deleted'){{window.location.href='/';}}
            else setTimeout(check,1000);
        }}catch(e){{setTimeout(check,2000);}}
    }} check();
    </script></body></html>
    """)


@app.post("/audit/{report_id}/cancel")
async def cancel_audit(report_id: int, db: Session = Depends(get_db)):
    """Отменяет активную проверку."""
    rep = db.query(AuditReport).filter(AuditReport.id == report_id).first()
    if not rep:
        return JSONResponse({"status": "not_found"}, status_code=404)
    if rep.status == "completed":
        return JSONResponse({"status": "already_completed"}, status_code=400)
    # Устанавливаем флаг отмены в трекере
    if report_id in PROGRESS_TRACKER:
        PROGRESS_TRACKER[report_id]["cancel"] = True
    else:
        # Если задача ещё не стартовала или уже завершилась
        pass
    print(f"[CANCEL] Отмена отчёта #{report_id}")
    return JSONResponse({"status": "cancelling"})


@app.get("/audit/{report_id}/status")
async def get_audit_status(report_id: int, db: Session = Depends(get_db)):
    rep = db.query(AuditReport).filter(AuditReport.id == report_id).first()
    prog = PROGRESS_TRACKER.get(report_id, {"processed": 0, "total": 0})
    return JSONResponse({"status": rep.status if rep else "deleted",
                         "processed": prog.get("processed", 0), "total": prog.get("total", 0)})


@app.get("/audit/{report_id}/result", response_class=HTMLResponse)
async def audit_result_page(report_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rep = db.query(AuditReport).filter(AuditReport.id == report_id).first()
    if not rep or rep.status != "completed":
        return RedirectResponse(url=f"/audit/{report_id}/progress")

    report_data = json.loads(rep.report_json) if rep.report_json else []
    verdict_data = json.loads(rep.verdict_json) if rep.verdict_json else None

    rows = ""
    categories_in_report = set()
    for item in report_data:
        st = str(item.get("status", ""))
        cls = "safe" if "Разрешено" in st else ("danger" if "Запрещено" in st else "warn")
        cat = item.get("category", "Прочее")
        categories_in_report.add(cat)
        cve_count = item.get("cve_count", 0)
        cve_html = ""
        if cve_count > 0:
            cve_ids = ", ".join([v.get("cve", "") for v in item.get("cve_list", [])[:3]])
            cve_html = f"<br><small style='color:#e53e3e;'>🔒 {cve_count} уязв.: {cve_ids}</small>"
        rows += f"""<tr data-category='{cls}' data-type='{cat}'>
            <td style='padding:12px;border-bottom:1px solid #e2e8f0;word-break:break-word;'><b>{item.get('name')}</b><br><small style='color:#718096;'>(v.{item.get('version')})</small>{cve_html}</td>
            <td style='padding:12px;border-bottom:1px solid #e2e8f0;word-break:break-word;'>{item.get('license')}</td>
            <td style='padding:12px;border-bottom:1px solid #e2e8f0;word-break:break-word;'><span class='{cls}'>{st}</span></td>
            <td style='padding:12px;border-bottom:1px solid #e2e8f0;word-break:break-word;text-align:center;width:120px;'>{_category_badge(cat)}</td>
        </tr>"""

    cat_options = "".join([f'<option value="{c}">{c}</option>' for c in sorted(categories_in_report)])

    verdict_html = ""
    if verdict_data:
        v = verdict_data["verdict"]
        color = "#e53e3e" if "❌" in v else ("#dd6b20" if "⚠️" in v else "#2f855a")
        bg = "#fff5f5" if "❌" in v else ("#fffaf0" if "⚠️" in v else "#f0fff4")
        crit = f'<p style="margin:10px 0 0 0;color:#c53030;font-size:13px;"><b>Запрещённые:</b> {", ".join(verdict_data["critical_list"])}</p>' if verdict_data.get("critical_list") else ""
        warn = f'<p style="margin:5px 0 0 0;color:#c05621;font-size:13px;"><b>Требуют внимания:</b> {", ".join(verdict_data["warning_list"])}</p>' if verdict_data.get("warning_list") else ""
        cve_info = f'<p style="margin:5px 0 0 0;color:#e53e3e;font-size:13px;"><b>🔒 Уязвимости:</b> обнаружено {verdict_data.get("cve_total", 0)} CVE</p>' if verdict_data.get("cve_total", 0) > 0 else ""
        verdict_html = f"""<div style="background:{bg};border-left:6px solid {color};padding:20px 25px;border-radius:8px;margin-bottom:25px;">
            <h3 style="margin:0 0 8px 0;color:{color};font-size:18px;">ИТОГОВЫЙ ВЕРДИКТ: {v}</h3>
            <p style="margin:0;color:#4a5568;font-size:14px;line-height:1.6;">{verdict_data["reason"]}</p>{crit}{warn}{cve_info}</div>"""

    total_rows = len(report_data)

    limit_notice = ""
    if user and not (user.role == "admin" or user.subscription_plan in ["Pro", "Unlimited"]) and rep.total_count > FREE_COMPONENTS_LIMIT:
        hidden = rep.total_count - FREE_COMPONENTS_LIMIT
        limit_notice = f"""
        <div style="background: #fffaf0; border-left: 5px solid #dd6b20; padding: 15px 20px; border-radius: 8px; margin-bottom: 20px;">
            <b style="color: #c05621;">🔒 Показано {FREE_COMPONENTS_LIMIT} из {rep.total_count} компонентов</b>
            <p style="margin: 5px 0 10px 0; color: #4a5568; font-size: 13px;">Скрыто ещё {hidden} компонентов. Для полного доступа выберите тариф:</p>
            <a href="/pricing" style="background: #3182ce; color: white; padding: 8px 16px; border-radius: 4px; text-decoration: none; font-weight: 600; font-size: 13px;">💎 Перейти на Pro</a>
        </div>
        """

    return HTMLResponse(content=f"""
    <!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Результаты аудита</title>
    <style>
        body{{font-family:sans-serif;max-width:1150px;margin:40px auto;padding:20px;background:#f7fafc;color:#2d3748;}}
        .card{{background:white;padding:35px;border-radius:8px;box-shadow:0 4px 6px rgba(0,0,0,0.05);border-top:4px solid #1a365d;margin-bottom:20px;}}
        .safe{{color:#2f855a;font-weight:bold;}}.danger{{color:#e53e3e;font-weight:bold;}}.warn{{color:#dd6b20;font-weight:bold;}}
        table{{width:100%;border-collapse:collapse;}}
        th{{background:#1a365d;color:white;padding:12px;text-align:left;cursor:pointer;user-select:none;position:relative;}}
        th:hover{{background:#2a4a7f;}}
        th .sort-arrow{{opacity:0.5;font-size:11px;margin-left:5px;}}
        th.sorted-asc .sort-arrow::after{{content:" ▲";opacity:1;}}
        th.sorted-desc .sort-arrow::after{{content:" ▼";opacity:1;}}
        th:not(.sorted-asc):not(.sorted-desc) .sort-arrow::after{{content:" ⇅";}}
        .btn{{display:inline-block;background:#3182ce;color:white;padding:10px 20px;border-radius:4px;text-decoration:none;font-weight:600;margin-right:10px;}}
        .filter-btn{{background:white;color:#2d3748;border:1px solid #cbd5e0;padding:8px 16px;border-radius:6px;cursor:pointer;font-weight:600;font-size:13px;transition:0.2s;}}
        .filter-btn:hover{{background:#edf2f7;}}
        .filter-btn.active{{background:#3182ce;color:white;border-color:#3182ce;}}
        .search-box{{padding:8px 12px;border:1px solid #cbd5e0;border-radius:6px;font-size:14px;width:240px;}}
    </style></head><body>
    <div class="card">
        <h2 style="margin-top:0;">Результаты аудита: {rep.filename}</h2>
        <p>Проанализировано компонентов: <b>{rep.total_count}</b> | Найдено уязвимостей: <b style="color:#e53e3e;">{rep.cve_count or 0}</b></p>
        {verdict_html}
        {limit_notice}
        <div style="margin-bottom:20px;">
            <a href="/" class="btn">← На главную</a>
            <a href="/dashboard" class="btn" style="background:#718096;">Личный кабинет</a>
            {f'<a href="/download_excel/{rep.excel_filename}" class="btn" style="background:#2f855a;">📊 Excel</a>' if rep.excel_filename else ""}
        </div>
        <h3>Детальная ведомость</h3>
        {STATUS_LEGEND_HTML}

        <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:15px;">
            <button class="filter-btn active" onclick="filterRows('all', this)">Все ({total_rows})</button>
            <button class="filter-btn" onclick="filterRows('danger', this)">❌ Запрещено ({rep.danger_count})</button>
            <button class="filter-btn" onclick="filterRows('warn', this)">⚠️ Требует внимания ({rep.warn_count})</button>
            <button class="filter-btn" onclick="filterRows('safe', this)">✅ Разрешено ({rep.safe_count})</button>
            <input type="text" id="searchBox" class="search-box" placeholder="🔍 Поиск по имени..." oninput="applyFilters()">
            <select id="categoryFilter" class="search-box" onchange="applyFilters()" style="width:220px;">
                <option value="all">📂 Все категории</option>
                {cat_options}
            </select>
            <span id="counter" style="margin-left:auto;font-size:13px;color:#4a5568;">Показано: <b>{total_rows}</b> из {total_rows}</span>
        </div>

        <table id="resultsTable">
            <thead>
                <tr>
                    <th onclick="sortTable(0)">Компонент <span class="sort-arrow"></span></th>
                    <th onclick="sortTable(1)">Лицензия <span class="sort-arrow"></span></th>
                    <th onclick="sortTable(2)">Статус <span class="sort-arrow"></span></th>
                    <th onclick="sortTable(3)" style="text-align:center;width:120px;">Категория <span class="sort-arrow"></span></th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </div>
    {FOOTER_HTML}

    <script>
    var currentFilter = 'all';
    var currentSort = {{col: -1, dir: 'asc'}};

    function applyFilters() {{
        var searchVal = (document.getElementById('searchBox').value || '').toLowerCase().trim();
        var catFilter = document.getElementById('categoryFilter').value;
        var rows = document.querySelectorAll('#resultsTable tbody tr');
        var visible = 0;
        rows.forEach(function(row) {{
            var statusCat = row.getAttribute('data-category');
            var typeCat = row.getAttribute('data-type');
            var nameText = row.cells[0].innerText.toLowerCase();
            var matchStatus = (currentFilter === 'all' || statusCat === currentFilter);
            var matchCategory = (catFilter === 'all' || typeCat === catFilter);
            var matchSearch = (!searchVal || nameText.indexOf(searchVal) !== -1);
            if (matchStatus && matchCategory && matchSearch) {{
                row.style.display = '';
                visible++;
            }} else {{
                row.style.display = 'none';
            }}
        }});
        document.getElementById('counter').innerHTML = 'Показано: <b>' + visible + '</b> из {total_rows}';
    }}

    function filterRows(category, btn) {{
        currentFilter = category;
        document.querySelectorAll('.filter-btn').forEach(function(b) {{ b.classList.remove('active'); }});
        btn.classList.add('active');
        applyFilters();
    }}

    function sortTable(col) {{
        var table = document.getElementById('resultsTable');
        var tbody = table.querySelector('tbody');
        var rows = Array.from(tbody.querySelectorAll('tr'));
        var headers = table.querySelectorAll('th');

        var dir = 'asc';
        if (currentSort.col === col && currentSort.dir === 'asc') dir = 'desc';
        currentSort = {{col: col, dir: dir}};

        headers.forEach(function(h, i) {{
            h.classList.remove('sorted-asc', 'sorted-desc');
            if (i === col) h.classList.add(dir === 'asc' ? 'sorted-asc' : 'sorted-desc');
        }});

        rows.sort(function(a, b) {{
            var aVal = a.cells[col].innerText.toLowerCase().trim();
            var bVal = b.cells[col].innerText.toLowerCase().trim();
            if (aVal < bVal) return dir === 'asc' ? -1 : 1;
            if (aVal > bVal) return dir === 'asc' ? 1 : -1;
            return 0;
        }});

        rows.forEach(function(r) {{ tbody.appendChild(r); }});
        applyFilters();
    }}
    </script>
    </body></html>
    """)


@app.get("/about", response_class=HTMLResponse)
async def about_page(user: User = Depends(get_current_user)):
    info = get_version_info()
    changelog_html = ""
    for entry in info["changelog"]:
        changes_li = "".join([f"<li>{c}</li>" for c in entry["changes"]])
        changelog_html += f"""
        <div style="border-left:4px solid #3182ce;padding:15px 20px;margin-bottom:20px;background:#f8fafc;border-radius:6px;">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:10px;">
                <h3 style="margin:0;color:#1a365d;font-size:22px;">v{entry['version']}</h3>
                <span style="color:#718096;font-size:13px;">{entry['date']}</span>
            </div>
            <ul style="margin:0;padding-left:20px;font-size:14px;color:#2d3748;line-height:1.8;">
                {changes_li}
            </ul>
        </div>"""

    return HTMLResponse(content=f"""
    <!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8">
    <title>О сервисе Компонент-Эксперт — аудит ПО по ПП 1236</title>
    <meta name="description" content="Информация о платформе «Компонент-Эксперт»: назначение, технологии, история версий, ссылки. Автоматизированный аудит ПО на соответствие ПП РФ № 1236.">
    <link rel="canonical" href="https://reestr-audit.ru/about">
    <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E%F0%9F%9B%A1%EF%B8%8F%3C/text%3E%3C/svg%3E">
    <style>
        body {{ font-family: -apple-system, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #f7fafc; color: #2d3748; }}
        .nav {{ display: flex; justify-content: space-between; padding: 15px 0; border-bottom: 1px solid #e2e8f0; margin-bottom: 30px; font-size: 14px; flex-wrap: wrap; gap: 10px; }}
        .nav-brand {{ font-weight: 800; color: #1a365d; font-size: 16px; }}
        .card {{ background: white; padding: 40px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border-top: 4px solid #1a365d; margin-bottom: 20px; }}
        h1 {{ color: #1a365d; margin-top: 0; }}
        .version-badge {{ display: inline-block; background: #3182ce; color: white; padding: 6px 16px; border-radius: 20px; font-size: 14px; font-weight: 600; margin-left: 10px; }}
        .tech {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 15px 0; }}
        .tech span {{ background: #edf2f7; padding: 4px 12px; border-radius: 12px; font-size: 13px; color: #2d3748; }}
        a {{ color: #3182ce; }}
    </style></head><body>
    <div class="nav"><div class="nav-brand">🛡️ Компонент-Эксперт</div><div>{_build_nav(user)}</div></div>

    <div class="card">
        <h1>О сервисе <span class="version-badge">v{info['version']}</span></h1>
        <p><b>Платформа «Компонент-Эксперт»</b> — веб-сервис автоматизированного аудита программного обеспечения на соответствие Постановлению Правительства РФ № 1236.</p>

        <h3 style="color:#1a365d;margin-top:30px;">Дата сборки</h3>
        <p style="font-size:14px;color:#4a5568;">{info['build_date']}</p>

        <h3 style="color:#1a365d;margin-top:30px;">Технологии</h3>
        <div class="tech">
            <span>Python 3.12</span>
            <span>FastAPI</span>
            <span>SQLAlchemy 2.0</span>
            <span>SQLite</span>
            <span>GigaChat (OAuth 2.0)</span>
            <span>OSV API</span>
            <span>Docker</span>
            <span>Nginx</span>
        </div>

        <h3 style="color:#1a365d;margin-top:30px;">Ссылки</h3>
        <ul style="font-size:14px;line-height:1.8;">
            <li><a href="https://reestr.digital.gov.ru/" target="_blank">Единый реестр российского ПО</a></li>
            <li><a href="/terms">Пользовательское соглашение</a></li>
            <li><a href="/feedback">Обратная связь</a></li>
        </ul>
    </div>

    <div class="card">
        <h1 style="font-size:26px;">История версий</h1>
        {changelog_html}
    </div>

    {FOOTER_HTML}
    </body></html>
    """)


@app.get("/download_excel/{filename}")
async def download_excel(filename: str):
    fp = os.path.join(PDF_DIR, filename)
    if os.path.exists(fp):
        return FileResponse(fp, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=filename)
    return HTMLResponse("Файл не найден", status_code=404)


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, filter_mode: str = "all", db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return HTMLResponse("<h1 style='color:red;text-align:center;font-family:sans-serif;margin-top:100px;'>403 Доступ запрещён</h1>", status_code=403)

    query = db.query(User)
    if filter_mode == "real":
        query = query.filter((User.is_test == False) | (User.is_test == None))
    elif filter_mode == "test":
        query = query.filter(User.is_test == True)
    all_users = query.all()
    all_reports = db.query(AuditReport).all()
    all_rules = db.query(LicenseRule).order_by(LicenseRule.component_key).all()
    all_feedback = db.query(Feedback).order_by(Feedback.created_at.desc()).all()
    total_visits = db.query(VisitLog).count()
    # --- Статистика AI-кэша ---
    try:
        cache_total = db.query(AILicenseCache).count()
        cache_success = db.query(AILicenseCache).filter(AILicenseCache.is_failure == False).count()
        cache_failures = db.query(AILicenseCache).filter(AILicenseCache.is_failure == True).count()
        cache_hits_raw = db.query(AILicenseCache).all()
        total_hits = sum((c.hit_count or 0) for c in cache_hits_raw)
        # Экономия: 15 секунд на запрос к ИИ
        savings_sec = total_hits * 15
        savings_min = savings_sec / 60
        # Экономия запросов к API (примерная стоимость ~0.01 USD за 1000 токенов, среднее ~500 токенов)
        savings_requests = total_hits
    except Exception as e:
        print(f"[CACHE STATS] Ошибка: {e}")
        cache_total = 0
        cache_success = 0
        cache_failures = 0
        total_hits = 0
        savings_sec = 0
        savings_min = 0
        savings_requests = 0
    unread_feedback = sum(1 for f in all_feedback if not f.is_read)
    now = datetime.utcnow()
    online_count = sum(1 for u in all_users if u.last_active and (now - u.last_active) < timedelta(minutes=15))
    week_ago = now - timedelta(days=7)
    monthly_ago = now - timedelta(days=30)
    active_7d = sum(1 for u in all_users if u.last_active and u.last_active > week_ago)
    active_30d = sum(1 for u in all_users if u.last_active and u.last_active > monthly_ago)
    # Активные из них — не админы
    real_7d = sum(1 for u in all_users if u.role != "admin" and u.last_active and u.last_active > week_ago)
    # Регистрации за 7 дней
    new_7d = sum(1 for u in all_users if u.created_at and u.created_at > week_ago)

    users_html = ""
    for u in all_users:
        is_online = u.last_active and (now - u.last_active) < timedelta(minutes=15)
        status_badge = "🟢 Онлайн" if is_online else "⚪ Офлайн"
        if u.subscription_status == "Blocked":
            status_badge = "🔴 Заблокирован"
        plan_selector = f"""<select onchange="changePlan(this, {u.id})" style="padding:4px;font-size:13px;border-radius:4px;border:1px solid #cbd5e0;">
            <option value="Free" {'selected' if u.subscription_plan == 'Free' else ''}>Free</option>
            <option value="Pro" {'selected' if u.subscription_plan == 'Pro' else ''}>Pro</option>
            <option value="Unlimited" {'selected' if u.subscription_plan == 'Unlimited' else ''}>🔥 Безлимит</option>
        </select>"""
        block_action = "Block" if u.subscription_status != "Blocked" else "Unblock"
        block_text = "Блок" if u.subscription_status != "Blocked" else "Разблок"
        block_color = "#e53e3e" if u.subscription_status != "Blocked" else "#2f855a"
        checks_info = f"<small style='color:#718096;'>({u.free_checks_used or 0}/{FREE_CHECKS_LIMIT})</small>" if u.subscription_plan == "Free" else ""
        actions = f"""<div style="display:flex;gap:5px;flex-wrap:wrap;">
            <button onclick="toggleBlock({u.id}, '{block_action}')" style="background:{block_color};color:white;border:none;border-radius:4px;padding:4px 8px;font-size:12px;cursor:pointer;font-weight:600;">{block_text}</button>
            <button onclick="resetPwd({u.id}, '{u.email}')" style="background:#d69e2e;color:white;border:none;border-radius:4px;padding:4px 8px;font-size:12px;cursor:pointer;font-weight:600;">🔑</button>
            <button onclick="resetChecks({u.id}, '{u.email}')" style="background:#805ad5;color:white;border:none;border-radius:4px;padding:4px 8px;font-size:12px;cursor:pointer;font-weight:600;" title="Сбросить счётчик проверок">♻️</button>
            <button onclick="delUser({u.id}, '{u.email}')" style="background:#e53e3e;color:white;border:none;border-radius:4px;padding:4px 8px;font-size:12px;cursor:pointer;font-weight:600;">🗑️</button>
        </div>"""
        test_badge = " <span style='background:#fefcbf; color:#744210; padding:2px 6px; border-radius:4px; font-size:10px; font-weight:600;'>ТЕСТ</span>" if u.is_test else ""
        users_html += f"<tr><td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{u.id}</td><td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{u.company_name}</td><td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{u.email}{test_badge}</td><td style='padding:10px;border-bottom:1px solid #e2e8f0;'><b>{u.role}</b></td><td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{plan_selector} {checks_info}</td><td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{status_badge}</td><td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{actions}</td></tr>"

    reports_html = "".join([
        f"<tr><td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{r.id}</td>"
        f"<td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{r.owner.email if r.owner else '—'}</td>"
        f"<td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{r.filename}</td>"
        f"<td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{r.cve_count or 0}</td>"
        f"<td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{r.created_at.strftime('%Y-%m-%d %H:%M')}</td>"
        f"<td style='padding:10px;border-bottom:1px solid #e2e8f0;'><button onclick='delReport({r.id})' style='background:#e53e3e;color:white;border:none;border-radius:4px;padding:4px 8px;font-size:12px;cursor:pointer;'>Удалить</button></td></tr>"
        for r in all_reports
    ])

    feedback_html = ""
    for f in all_feedback:
        row_bg = "#ffffff" if f.is_read else "#fffaf0"
        unread_mark = "" if f.is_read else "🔵 "
        mark_btn = "" if f.is_read else f'<button onclick="markRead({f.id})" style="background:#3182ce;color:white;border:none;border-radius:4px;padding:4px 8px;font-size:12px;cursor:pointer;">✓ Прочитано</button>'
        feedback_html += f"""<tr style="background:{row_bg};">
            <td style='padding:10px;border-bottom:1px solid #e2e8f0;vertical-align:top;'><b>{unread_mark}#{f.id}</b><br><small>{f.created_at.strftime('%Y-%m-%d %H:%M')}</small></td>
            <td style='padding:10px;border-bottom:1px solid #e2e8f0;vertical-align:top;'><b>{f.name}</b><br><a href="mailto:{f.email}" style="color:#3182ce;font-size:12px;">{f.email}</a></td>
            <td style='padding:10px;border-bottom:1px solid #e2e8f0;vertical-align:top;'><b style="color:#2b6cb0;font-size:13px;">{f.subject or '—'}</b></td>
            <td style='padding:10px;border-bottom:1px solid #e2e8f0;vertical-align:top;font-size:13px;'>{f.message}</td>
            <td style='padding:10px;border-bottom:1px solid #e2e8f0;vertical-align:top;'>
                <div style="display:flex;gap:5px;flex-wrap:wrap;">
                    {mark_btn}
                    <button onclick="delFeedback({f.id})" style="background:#e53e3e;color:white;border:none;border-radius:4px;padding:4px 8px;font-size:12px;cursor:pointer;">🗑️</button>
                </div>
            </td>
        </tr>"""

    feedback_badge = f' <span style="background:#e53e3e;color:white;border-radius:10px;padding:2px 8px;font-size:11px;margin-left:8px;">{unread_feedback} новых</span>' if unread_feedback > 0 else ""

    return HTMLResponse(content=f"""
    <!DOCTYPE html><html><head><meta charset="UTF-8"><title>Админ-панель</title>
    <style>body{{font-family:sans-serif;max-width:1200px;margin:0 auto;padding:20px;background:#f7fafc;}}
    .nav{{display:flex;justify-content:space-between;padding:15px 0;border-bottom:1px solid #e2e8f0;margin-bottom:30px;font-size:14px;flex-wrap:wrap;gap:10px;}}
    .nav-brand{{font-weight:800;color:#1a365d;font-size:16px;}}
    .card{{background:white;padding:30px;border-radius:8px;margin-bottom:20px;border-top:4px solid #1a365d;}}
    table{{width:100%;border-collapse:collapse;}} th{{background:#1a365d;color:white;padding:12px;text-align:left;font-size:13px;}}
    .stats{{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:20px;}}
    .stat{{background:#edf2f7;padding:15px 25px;border-radius:6px;flex:1;min-width:180px;border-left:4px solid #3182ce;}}
    .stat h4{{margin:0;color:#4a5568;font-size:13px;}} .stat p{{margin:5px 0 0 0;font-size:22px;font-weight:bold;color:#1a365d;}}
    </style></head><body>
    <div class="nav"><div class="nav-brand">🛡️ Компонент-Эксперт — Админ</div><div>{_build_nav(user)}</div></div>
    <div class="card">
    <h2 style="margin-top:0;">👑 Панель администратора</h2>
    <div class="stats">
        <div class="stat"><h4>Пользователей</h4><p>{len(all_users)}</p></div>
        <div class="stat" style="border-left-color:#2f855a;"><h4>Онлайн</h4><p>{online_count}</p></div>
        <div class="stat" style="border-left-color:#d69e2e;"><h4>Отчётов</h4><p>{len(all_reports)}</p></div>
        <div class="stat" style="border-left-color:#805ad5;"><h4>Обращений</h4><p>{len(all_feedback)}{(' <small style="color:#e53e3e;font-size:13px;">'+str(unread_feedback)+' нов.</small>') if unread_feedback else ''}</p></div>
        <div class="stat" style="border-left-color:#3182ce;"><h4>Просмотров</h4><p>{total_visits}</p></div>
        <div class="stat" style="border-left-color:#3182ce;"><h4>📊 Активные за 7 дней</h4><p>{active_7d} <small style="color:#718096;font-size:13px;">({real_7d} без админов)</small></p></div>
        <div class="stat" style="border-left-color:#805ad5;"><h4>📈 Активные за 30 дней</h4><p>{active_30d}</p></div>
        <div class="stat" style="border-left-color:#38a169;"><h4>🧠 Кэш ИИ</h4><p>{cache_total} <small style="color:#4a5568;font-size:14px;">записей</small></p></div>
        <div class="stat" style="border-left-color:#805ad5;"><h4>⚡ Хитов кэша</h4><p>{total_hits} <small style="color:#4a5568;font-size:14px;">(≈{savings_min:.1f} мин)</small></p></div>
    </div>
    </div>

    <div class="card" style="border-top-color:#38a169; background:linear-gradient(135deg,#f0fff4 0%,#ffffff 100%);">
        <h3 style="margin-top:0; color:#1a365d;">📅 Сводка за последние 7 дней</h3>
        <div style="display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px;">
            <div style="background:white; padding:14px 18px; border-radius:8px; border-left:4px solid #3182ce;">
                <div style="font-size:11px; color:#718096; text-transform:uppercase; letter-spacing:0.5px;">Новые регистрации</div>
                <div style="font-size:24px; font-weight:700; color:#2b6cb0; margin-top:4px;">{new_7d}</div>
            </div>
            <div style="background:white; padding:14px 18px; border-radius:8px; border-left:4px solid #38a169;">
                <div style="font-size:11px; color:#718096; text-transform:uppercase; letter-spacing:0.5px;">Заходили в сервис</div>
                <div style="font-size:24px; font-weight:700; color:#2f855a; margin-top:4px;">{active_7d}</div>
            </div>
            <div style="background:white; padding:14px 18px; border-radius:8px; border-left:4px solid #dd6b20;">
                <div style="font-size:11px; color:#718096; text-transform:uppercase; letter-spacing:0.5px;">Онлайн сейчас</div>
                <div style="font-size:24px; font-weight:700; color:#c05621; margin-top:4px;">{online_count}</div>
            </div>
            <div style="background:white; padding:14px 18px; border-radius:8px; border-left:4px solid #805ad5;">
                <div style="font-size:11px; color:#718096; text-transform:uppercase; letter-spacing:0.5px;">Всего пользователей</div>
                <div style="font-size:24px; font-weight:700; color:#6b46c1; margin-top:4px;">{len(all_users)}</div>
            </div>
        </div>
    </div>

    <div class="card" style="overflow-x:auto; border-top-color:#805ad5;">
    <h3 style="margin-top:0;">📮 Обратная связь{feedback_badge}</h3>
    <p style="font-size:12px;color:#718096;">Сообщения от пользователей. Отмечайте прочитанные, удаляйте ненужные.</p>
    <table>
        <tr><th>Дата</th><th>Отправитель</th><th>Тема</th><th>Сообщение</th><th>Действие</th></tr>
        {feedback_html if feedback_html else '<tr><td colspan="5" style="padding:20px;text-align:center;color:#718096;">Пока нет обращений</td></tr>'}
    </table>
    </div>

    <div class="card" style="overflow-x:auto;">
    <h3 style="margin-top:0;">Управление пользователями</h3>
    <p style="font-size:12px;color:#718096;">♻️ — сбросить счётчик бесплатных проверок</p>
    <div style="display:flex; gap:10px; margin:15px 0; flex-wrap:wrap;">
        <a href="/admin?filter_mode=all" style="padding:8px 16px; border-radius:6px; text-decoration:none; font-weight:600; font-size:13px; {'background:#3182ce; color:white;' if filter_mode == 'all' else 'background:#edf2f7; color:#2d3748;'}">👥 Все ({len(all_users)})</a>
        <a href="/admin?filter_mode=real" style="padding:8px 16px; border-radius:6px; text-decoration:none; font-weight:600; font-size:13px; {'background:#38a169; color:white;' if filter_mode == 'real' else 'background:#edf2f7; color:#2d3748;'}">✅ Реальные</a>
        <a href="/admin?filter_mode=test" style="padding:8px 16px; border-radius:6px; text-decoration:none; font-weight:600; font-size:13px; {'background:#dd6b20; color:white;' if filter_mode == 'test' else 'background:#edf2f7; color:#2d3748;'}">🧪 Тестовые</a>
    </div>
    <table><tr><th>ID</th><th>Компания</th><th>Email</th><th>Роль</th><th>Тариф / Проверки</th><th>Статус</th><th>Действия</th></tr>{users_html}</table>
    </div>

    <div class="card" style="border-top-color:#38a169;">
    <h3 style="margin-top:0;">🧠 Кэш ИИ-ответов</h3>
    <p style="font-size:13px;color:#4a5568;">Кэш хранит ответы GigaChat на 90 дней (или 1 час для неудачных запросов). При повторной проверке того же компонента ИИ не вызывается — экономится время и деньги.</p>
    <div style="display:flex;gap:20px;flex-wrap:wrap;margin:20px 0;">
        <div style="flex:1;min-width:180px;background:#f0fff4;padding:18px 22px;border-radius:6px;border-left:4px solid #38a169;">
            <div style="color:#4a5568;font-size:12px;">Всего записей</div>
            <div style="font-size:26px;font-weight:bold;color:#2f855a;">{cache_total}</div>
        </div>
        <div style="flex:1;min-width:180px;background:#ebf8ff;padding:18px 22px;border-radius:6px;border-left:4px solid #3182ce;">
            <div style="color:#4a5568;font-size:12px;">Успешных ответов</div>
            <div style="font-size:26px;font-weight:bold;color:#2b6cb0;">{cache_success}</div>
        </div>
        <div style="flex:1;min-width:180px;background:#fffaf0;padding:18px 22px;border-radius:6px;border-left:4px solid #dd6b20;">
            <div style="color:#4a5568;font-size:12px;">Неудачных</div>
            <div style="font-size:26px;font-weight:bold;color:#c05621;">{cache_failures}</div>
        </div>
        <div style="flex:1;min-width:180px;background:#faf5ff;padding:18px 22px;border-radius:6px;border-left:4px solid #805ad5;">
            <div style="color:#4a5568;font-size:12px;">Хитов кэша</div>
            <div style="font-size:26px;font-weight:bold;color:#6b46c1;">{total_hits}</div>
        </div>
    </div>
    <div style="background:#edf2f7;padding:14px 18px;border-radius:6px;font-size:14px;color:#2d3748;">
        💰 <b>Экономия:</b> примерно <b>{savings_requests}</b> запросов к GigaChat и <b>{savings_min:.1f} минут</b> ожидания пользователями (при среднем времени ответа ИИ ≈ 15 сек).
    </div>
    <div style="margin-top:15px;">
        <form method="POST" action="/admin/clear-ai-cache" style="display:inline;">
            <button type="submit" onclick="return confirm('Очистить весь кэш ИИ? Это удалит все сохранённые ответы.');" style="background:#e53e3e;color:white;border:none;border-radius:4px;padding:8px 16px;font-size:13px;cursor:pointer;font-weight:600;">🗑️ Очистить кэш</button>
        </form>
    </div>
    </div>

    <div class="card" style="overflow-x:auto;">
    <h3 style="margin-top:0;">Все проверки ({len(all_reports)})</h3>
    <table><tr><th>ID</th><th>Владелец</th><th>Файл</th><th>CVE</th><th>Дата</th><th>Действие</th></tr>{reports_html if reports_html else '<tr><td colspan="6" style="padding:20px;text-align:center;">Нет проверок</td></tr>'}</table>
    </div>

    <div class="card">
    <h3 style="margin-top:0;">База знаний ({len(all_rules)} правил)</h3>
    <div style="max-height:400px;overflow-y:auto;">
    <table><tr><th>Компонент</th><th>Лицензия</th><th>Статус</th></tr>
    {"".join([f"<tr><td style='padding:8px;border-bottom:1px solid #e2e8f0;'><b>{r.component_key}</b></td><td style='padding:8px;border-bottom:1px solid #e2e8f0;'>{r.license_name}</td><td style='padding:8px;border-bottom:1px solid #e2e8f0;'>{r.status}</td></tr>" for r in all_rules])}
    </table></div>
    </div>

    {FOOTER_HTML}
    <script>
    async function changePlan(sel, uid) {{
        var fd = new FormData();
        fd.append('user_id', uid); fd.append('plan', sel.value);
        await fetch('/admin/set-plan', {{method:'POST', body: fd}});
        location.reload();
    }}
    async function toggleBlock(uid, action) {{
        var fd = new FormData();
        fd.append('user_id', uid); fd.append('action', action);
        await fetch('/admin/toggle-block', {{method:'POST', body: fd}});
        location.reload();
    }}
    async function resetPwd(uid, email) {{
        if (!confirm('Сбросить пароль для ' + email + '?')) return;
        var fd = new FormData(); fd.append('user_id', uid);
        var r = await fetch('/admin/reset-password', {{method:'POST', body: fd}});
        var d = await r.json();
        alert('Новый пароль: ' + d.new_password);
    }}
    async function resetChecks(uid, email) {{
        if (!confirm('Сбросить счётчик проверок для ' + email + '?')) return;
        var fd = new FormData(); fd.append('user_id', uid);
        await fetch('/admin/reset-checks', {{method:'POST', body: fd}});
        location.reload();
    }}
    async function delUser(uid, email) {{
        if (!confirm('УДАЛИТЬ пользователя ' + email + '?')) return;
        var fd = new FormData(); fd.append('user_id', uid);
        await fetch('/admin/delete-user', {{method:'POST', body: fd}});
        location.reload();
    }}
    async function delReport(rid) {{
        if (!confirm('Удалить отчёт #' + rid + '?')) return;
        await fetch('/reports/delete/' + rid, {{method:'POST'}});
        location.reload();
    }}
    async function markRead(fid) {{
        await fetch('/admin/feedback/mark-read/' + fid, {{method:'POST'}});
        location.reload();
    }}
    async function delFeedback(fid) {{
        if (!confirm('Удалить обращение #' + fid + '?')) return;
        await fetch('/admin/feedback/delete/' + fid, {{method:'POST'}});
        location.reload();
    }}
    </script>
    </body></html>
    """)


@app.post("/admin/set-plan")
async def set_user_plan(request: Request, user_id: int = Form(...), plan: str = Form(...), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403)
    target = db.query(User).filter(User.id == user_id).first()
    if target and plan in ["Free", "Pro", "Unlimited"]:
        target.subscription_plan = plan
        db.commit()
    return JSONResponse({"status": "ok"})


@app.post("/admin/toggle-block")
async def toggle_block_user(request: Request, user_id: int = Form(...), action: str = Form(...), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403)
    target = db.query(User).filter(User.id == user_id).first()
    if target and target.id != user.id:
        target.subscription_status = "Blocked" if action == "Block" else "Active"
        db.commit()
    return JSONResponse({"status": "ok"})


@app.post("/admin/reset-password")
async def admin_reset_password(request: Request, user_id: int = Form(...), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403)
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404)
    new_pass = secrets.token_urlsafe(8)
    target.hashed_password = hash_password(new_pass)
    db.commit()
    return JSONResponse({"new_password": new_pass})


@app.post("/admin/reset-checks")
async def admin_reset_checks(request: Request, user_id: int = Form(...), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403)
    target = db.query(User).filter(User.id == user_id).first()
    if target:
        target.free_checks_used = 0
        db.commit()
    return JSONResponse({"status": "ok"})


@app.post("/admin/delete-user")
async def admin_delete_user(request: Request, user_id: int = Form(...), db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403)
    target = db.query(User).filter(User.id == user_id).first()
    if target and target.id != user.id:
        reports = db.query(AuditReport).filter(AuditReport.user_id == target.id).all()
        for r in reports:
            if r.excel_filename:
                fp = os.path.join(PDF_DIR, r.excel_filename)
                if os.path.exists(fp):
                    try: os.remove(fp)
                    except: pass
            db.delete(r)
        db.delete(target)
        db.commit()
    return JSONResponse({"status": "ok"})


@app.post("/admin/clear-ai-cache")
async def admin_clear_ai_cache(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403)
    deleted = db.query(AILicenseCache).delete()
    db.commit()
    print(f"[ADMIN] Очищено записей кэша: {deleted}")
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/feedback/mark-read/{feedback_id}")
async def admin_mark_feedback_read(feedback_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403)
    fb = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if fb:
        fb.is_read = True
        db.commit()
    return JSONResponse({"status": "ok"})


@app.post("/admin/feedback/delete/{feedback_id}")
async def admin_delete_feedback(feedback_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403)
    fb = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if fb:
        db.delete(fb)
        db.commit()
    return JSONResponse({"status": "ok"})
