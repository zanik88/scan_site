import asyncio
import hashlib
import io
import json
import os
import re
import secrets
import sqlite3
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

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./saas_audit.db")
SECRET_KEY = os.getenv("SECRET_KEY", "fallback-secret-key-change-in-production")
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"

YANDEX_GPT_API_KEY = os.getenv("YANDEX_GPT_API_KEY", "")
YANDEX_FOLDER_ID = os.getenv("YANDEX_FOLDER_ID", "")
GIGACHAT_API_KEY = os.getenv("GIGACHAT_API_KEY", "")

FREE_CHECKS_LIMIT = 5
FREE_COMPONENTS_LIMIT = 10

PROGRESS_TRACKER = {}

app = FastAPI(title="Платформа «Компонент-Эксперт» - ПП РФ № 1236", version="9.0.0")


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


async def _call_gigachat(session: aiohttp.ClientSession, prompt: str) -> Optional[dict]:
    if not GIGACHAT_API_KEY:
        return None
    try:
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        headers = {"Authorization": f"Bearer {GIGACHAT_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "GigaChat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.1}
        async with session.post(url, headers=headers, json=payload, ssl=False, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status == 200:
                data = await resp.json()
                parsed = _extract_json(data["choices"][0]["message"]["content"])
                if parsed:
                    parsed["provider"] = "GigaChat"
                    return parsed
    except Exception as e:
        print(f"[AI] GigaChat error: {e}")
    return None


async def ask_ai_for_license(component_name: str, provider: str = "auto") -> tuple:
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
                return (result["license"], result.get("status", "⚠️ Требует внимания"), f"{rec} (ИИ: {result['provider']})")

    print(f"[AI] ❌ Все ИИ недоступны для '{component_name}'.")
    return ("Не определена", "⚠️ Требует внимания", f"Не удалось определить лицензию для '{component_name}'. Требуется ручная проверка.")


# ==========================================
# ОПРЕДЕЛЕНИЕ КАТЕГОРИЙ
# ==========================================
def _detect_category(name: str) -> str:
    n = (name or "").lower().strip()
    if not n:
        return "Прочее"

    # ВАЖНО: СУБД проверяем РАНЬШЕ игровых движков, чтобы "community" не
    # попадало под "unity". Используем границы слов через regex.
    def _has_word(text, word):
        return re.search(r'\b' + re.escape(word) + r'\b', text) is not None

    # СУБД и хранилища (первым делом — во избежание ложных срабатываний)
    db_keys = ["postgres", "mysql", "mariadb", "oracle", "sql server", "sqlite", "mongodb",
               "redis", "valkey", "clickhouse", "cassandra", "scylladb", "couchdb", "neo4j",
               "elasticsearch", "opensearch", "kafka", "rabbitmq", "zookeeper", "influxdb",
               "sap hana", "enterprisedb", "npgsql", "db2", "teradata", "firebird", "hive",
               "tibero", "tmax"]
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
    if not user:
        return False
    return user.role == "admin" or user.subscription_plan in ["Pro", "Unlimited"]


def get_free_checks_left(user: Optional[User], request: Request) -> int:
    if user and user.role == "admin":
        return 999
    if user and user.subscription_plan in ["Pro", "Unlimited"]:
        return 999
    if user:
        used = user.free_checks_used or 0
        return max(0, FREE_CHECKS_LIMIT - used)
    if request:
        guest_count = int(request.cookies.get("guest_audit_count", 0))
        return max(0, FREE_CHECKS_LIMIT - guest_count)
    return FREE_CHECKS_LIMIT


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
    line = line.strip()
    m = re.match(r'^([A-Za-z0-9_\-\.]+)\s*(==|>=|<=|~=|!=|>|<|=)\s*([^\s,;#]+)', line)
    if m:
        return m.group(1).strip(), m.group(3).strip()
    m = re.match(r'^["\']?([A-Za-z0-9_\-\.@/]+)["\']?\s*[:\s]\s*["\']?[\^~v=]?([\d][^\s,;"\']*)', line)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    if line.count(":") >= 2:
        parts = line.split(":")
        if len(parts) >= 3 and re.match(r'^[\d]', parts[-1]):
            return parts[1].strip(), parts[-1].strip()
    parts = re.split(r'[\t]+', line, maxsplit=1)
    if len(parts) >= 2 and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return line.strip(), "unknown"


def _is_garbage_component(name: str) -> bool:
    if not name:
        return True
    n = name.strip()
    if len(n) < 2:
        return True
    if n.startswith('['):
        return True
    if "," in n and len(n.split(",")) > 1:
        return True
    lower = n.lower()
    if lower.startswith(("author", "copyright", "company", "namespace", "project",
                          "creator", "maintainer", "owner", "publisher")):
        return True
    if lower in ("name", "название", "компонент", "component"):
        return True
    if " " in n and all(w[0].isupper() for w in n.split() if w):
        if not any(k in lower for k in ["visual", "studio", "code", "spring", "boot", "sql", "server",
                                         "red", "hat", "sap", "ibm", "amazon", "microsoft", "google",
                                         "apache", "oracle", "node", "docker", "kubernetes", "github",
                                         "gitlab", "open", "source", "enterprise", "foundation"]):
            return True
    return False


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
            for table in doc.tables:
                for row in table.rows:
                    row_vals = [c.text.strip() for c in row.cells if c.text.strip()]
                    if row_vals:
                        name = row_vals[0]
                        ver = row_vals[1] if len(row_vals) > 1 else "unknown"
                        if not _is_garbage_component(name):
                            extracted.append({"name": name, "version": ver})
            for p in doc.paragraphs:
                if p.text.strip():
                    parts = re.split(r'[\t:,]+', p.text.strip())
                    if parts and not _is_garbage_component(parts[0]):
                        extracted.append({"name": parts[0].strip(), "version": parts[1].strip() if len(parts) > 1 else "unknown"})
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
        else:
            text = file_bytes.decode("utf-8", errors="ignore")
            for line in text.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    name, ver = _split_name_version(line)
                    if not _is_garbage_component(name):
                        extracted.append({"name": name, "version": ver})
    except Exception as e:
        print(f"Parse error {filename}: {e}")
    # Нормализация: если "версия" на самом деле лицензия — сбрасываем
    for item in extracted:
        if _is_license_like(item.get("version", "")):
            item["version"] = "unknown"
    if not extracted:
        extracted = [{"name": filename.split(".")[0], "version": "1.0.0"}]
    return extracted


async def fetch_package_info_with_version(session, package_name, table_version, cached_rules,
                                          report_id, ai_provider="auto") -> dict:
    search_clean = sanitize_string(package_name)

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

        sem = asyncio.Semaphore(10)

        async def bounded(item):
            if PROGRESS_TRACKER.get(report_id, {}).get("cancel", False):
                return None
            async with sem:
                if PROGRESS_TRACKER.get(report_id, {}).get("cancel", False):
                    return None
                res = await fetch_package_info_with_version(
                    session, item["name"], item["version"], cached_rules, report_id, ai_provider)
                if report_id in PROGRESS_TRACKER:
                    PROGRESS_TRACKER[report_id]["processed"] += 1
                return res

        async with aiohttp.ClientSession() as session:
            tasks = [bounded(item) for item in items]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            if PROGRESS_TRACKER.get(report_id, {}).get("cancel", False):
                rep = db.query(AuditReport).filter(AuditReport.id == report_id).first()
                if rep:
                    db.delete(rep)
                    db.commit()
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
<div class="upload-box" style="background: #f8fafc; border: 2px dashed #cbd5e0; padding: 25px; border-radius: 6px; margin: 25px 0; text-align: center;">
    <h3 style="color: #1a365d; margin-top: 0;">📂 Загрузите файл, вставьте список или укажите Docker-образ</h3>
    <div style="margin-bottom: 20px;">
        <label style="font-size: 13px; font-weight: 600; color: #4a5568;">🧠 ИИ-анализ:</label>
        <select name="ai_provider" style="padding: 7px 14px; border-radius: 4px; border: 1px solid #cbd5e0;">
            <option value="auto" selected>🔀 Авто (YandexGPT → GigaChat → база)</option>
            <option value="yandex">YandexGPT</option>
            <option value="gigachat">GigaChat (Сбер)</option>
        </select>
    </div>
    <div style="display: flex; gap: 20px; flex-wrap: wrap; text-align: left; justify-content: center;">
        <div style="flex: 1; min-width: 240px; background: white; padding: 15px; border-radius: 6px; border: 1px solid #e2e8f0;">
            <h4 style="margin: 0 0 10px 0; color: #2d3748; font-size: 14px;">Способ 1: Файл</h4>
            <input type="file" name="file" accept=".txt,.xlsx,.xls,.docx,.pdf,.json" style="width: 100%;">
        </div>
        <div style="flex: 1; min-width: 240px; background: white; padding: 15px; border-radius: 6px; border: 1px solid #e2e8f0;">
            <h4 style="margin: 0 0 10px 0; color: #2d3748; font-size: 14px;">Способ 2: Текст</h4>
            <textarea name="text_input" maxlength="500" placeholder="fastapi==0.115.6&#10;pandas==2.2.3" style="width: 100%; min-height: 80px; padding: 8px; border: 1px solid #cbd5e0; border-radius: 4px; font-family: monospace;"></textarea>
        </div>
    </div>
    <div style="margin-top: 20px; padding-top: 20px; border-top: 1px dashed #cbd5e0;">
        <h4 style="margin: 0 0 10px 0; color: #2d3748; font-size: 14px;">🐳 Способ 3: Сканировать Docker-образ</h4>
        <input type="text" name="docker_image" placeholder="ubuntu:22.04 / python:3.12-slim / node:20-alpine" style="width: 100%; padding: 10px; border: 1px solid #cbd5e0; border-radius: 4px; font-family: monospace;">
        <div style="font-size: 11px; color: #718096; margin-top: 5px;">Система поднимет контейнер, определит базовую ОС и проверит пакеты.</div>
    </div>
</div>
"""

GUIDELINES_HTML = """
<div class="card" style="margin-top: 25px; background: #f8fafc; border-top: 4px solid #3182ce; padding: 20px; border-radius: 8px;">
    <h3 style="color: #1a365d; margin-top: 0;">📌 Рекомендации</h3>
    <ul style="font-size: 14px; color: #4a5568; line-height: 1.7;">
        <li><b>SBOM (CycloneDX/SPDX):</b> <code>.cdx.json</code>, <code>.spdx.json</code>, <code>package.json</code></li>
        <li><b>Word / PDF:</b> Maven-координаты, списки с тире.</li>
        <li><b>Текстом:</b> по одной строке <code>имя==версия</code></li>
        <li><b>Docker:</b> укажите <code>image:tag</code></li>
        <li><b>CVE:</b> автоматически проверяется через OSV API (только для компонентов с известной версией).</li>
    </ul>
</div>
"""


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
    if user:
        admin_link = " | <a href='/admin' style='color:#e53e3e;font-weight:700;text-decoration:none;'>Панель администратора</a>" if user.role == "admin" else ""
        return (f"<span style='color:#2d3748;'>👤 <b>{user.email}</b> <span style='color:#718096;font-size:12px;'>({user.role})</span></span>"
                f" | <a href='/dashboard' style='color:#3182ce;text-decoration:none;font-weight:600;'>Личный кабинет</a>"
                f"{admin_link} | <a href='/pricing' style='color:#3182ce;text-decoration:none;font-weight:600;'>Тарифы</a>"
                f" | {feedback_link}"
                f" | <a href='/logout' style='color:#718096;text-decoration:none;'>Выйти</a>")
    return ("<a href='/login' style='color:#3182ce;text-decoration:none;font-weight:600;'>Вход</a>"
            " | <a href='/register' style='background:#3182ce;color:white;padding:6px 14px;border-radius:4px;text-decoration:none;font-weight:600;'>Регистрация</a>"
            " | <a href='/pricing' style='color:#3182ce;text-decoration:none;font-weight:600;'>Тарифы</a>"
            f" | {feedback_link}")


def _free_plan_banner(user: Optional[User], request: Optional[Request]) -> str:
    if user and (user.role == "admin" or user.subscription_plan in ["Pro", "Unlimited"]):
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


@app.get("/health")
async def health():
    return {"status": "ok", "service": "component-expert", "version": "9.0.0"}


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
    <title>Компонент-Эксперт | ПП РФ № 1236</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; max-width: 900px; margin: 0 auto; padding: 20px; background: #f7fafc; color: #2d3748; }}
        .nav {{ display: flex; justify-content: space-between; padding: 15px 0; border-bottom: 1px solid #e2e8f0; margin-bottom: 30px; font-size: 14px; align-items: center; flex-wrap: wrap; gap: 10px; }}
        .nav-brand {{ font-weight: 800; color: #1a365d; font-size: 16px; }}
        .card {{ background: white; padding: 40px; border-radius: 8px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border-top: 4px solid #1a365d; }}
        h1 {{ color: #1a365d; text-align: center; }}
        .submit-btn {{ background: #2f855a; color: white; border: none; padding: 14px 32px; font-size: 15px; font-weight: 600; border-radius: 4px; cursor: pointer; width: 100%; margin-top: 15px; }}
        .submit-btn:hover {{ background: #276749; }}
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
    free_left = get_free_checks_left(user, request)
    unlimited = is_unlimited(user)

    if not unlimited and free_left <= 0:
        return RedirectResponse(url="/pricing", status_code=status.HTTP_303_SEE_OTHER)

    is_pro = unlimited

    if not unlimited and user:
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
async def register(company_name: str = Form(...), email: str = Form(...), password: str = Form(...),
                   terms_accepted: str = Form(None), db: Session = Depends(get_db)):
    if not terms_accepted:
        raise HTTPException(status_code=400, detail="Необходимо принять условия пользовательского соглашения")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email занят")
    assigned_role = "admin" if db.query(User).count() == 0 else "user"
    db.add(User(company_name=company_name, email=email, hashed_password=hash_password(password),
                role=assigned_role, subscription_plan="Pro" if assigned_role == "admin" else "Free",
                free_checks_used=0))
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
    <p>3.3. При обращении к внешним ИИ-провайдерам (YandexGPT, GigaChat) передаётся только название компонента, без содержимого файла.</p>
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
    <!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>Тарифы</title>
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
            <ul class="pf"><li>✔️ Безлимит проверок</li><li>✔️ Docker-сканер</li><li>✔️ Excel-отчёты</li><li>✔️ Приоритетная поддержка</li></ul></div>
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
        plan_badge = "💎 Профессиональный (безлимит)"
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
    <style>body{{font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f7fafc;}}
    .card{{background:white;padding:45px;border-radius:8px;border-top:5px solid #3182ce;text-align:center;max-width:480px;}}</style>
    </head><body><div class="card">
    <h2>Идёт анализ ПО</h2>
    <p>ИИ-агент проверяет зависимости и уязвимости...</p>
    <div style="width:100%;background:#e2e8f0;border-radius:4px;height:8px;margin-top:25px;">
        <div id="pf" style="width:0%;height:100%;background:#3182ce;transition:width 0.4s;"></div>
    </div>
    <p id="pt" style="font-size:13px;color:#4a5568;">Подготовка...</p>
    </div>
    <script>
    async function check(){{
        try{{
            const r = await fetch('/audit/{report_id}/status');
            const d = await r.json();
            if(d.total>0){{
                const pct = Math.round((d.processed/d.total)*100);
                document.getElementById('pf').style.width = pct + '%';
                document.getElementById('pt').innerText = `Анализ: ${{d.processed}}/${{d.total}} (${{pct}}%)`;
            }}
            if(d.status==='completed') window.location.href='/audit/{report_id}/result';
            else if(d.status==='failed'){{alert('Ошибка анализа');window.location.href='/';}}
            else setTimeout(check,1000);
        }}catch(e){{setTimeout(check,2000);}}
    }} check();
    </script></body></html>
    """)


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
            <td style='padding:12px;border-bottom:1px solid #e2e8f0;word-break:break-word;'><span style='background:#edf2f7;padding:3px 8px;border-radius:4px;font-size:12px;'>{cat}</span></td>
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
                    <th onclick="sortTable(3)">Категория <span class="sort-arrow"></span></th>
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


@app.get("/download_excel/{filename}")
async def download_excel(filename: str):
    fp = os.path.join(PDF_DIR, filename)
    if os.path.exists(fp):
        return FileResponse(fp, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=filename)
    return HTMLResponse("Файл не найден", status_code=404)


@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return HTMLResponse("<h1 style='color:red;text-align:center;font-family:sans-serif;margin-top:100px;'>403 Доступ запрещён</h1>", status_code=403)

    all_users = db.query(User).all()
    all_reports = db.query(AuditReport).all()
    all_rules = db.query(LicenseRule).order_by(LicenseRule.component_key).all()
    all_feedback = db.query(Feedback).order_by(Feedback.created_at.desc()).all()
    total_visits = db.query(VisitLog).count()
    unread_feedback = sum(1 for f in all_feedback if not f.is_read)
    now = datetime.utcnow()
    online_count = sum(1 for u in all_users if u.last_active and (now - u.last_active) < timedelta(minutes=15))

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
        users_html += f"<tr><td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{u.id}</td><td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{u.company_name}</td><td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{u.email}</td><td style='padding:10px;border-bottom:1px solid #e2e8f0;'><b>{u.role}</b></td><td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{plan_selector} {checks_info}</td><td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{status_badge}</td><td style='padding:10px;border-bottom:1px solid #e2e8f0;'>{actions}</td></tr>"

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
    <table><tr><th>ID</th><th>Компания</th><th>Email</th><th>Роль</th><th>Тариф / Проверки</th><th>Статус</th><th>Действия</th></tr>{users_html}</table>
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
