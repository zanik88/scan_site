#!/usr/bin/env python3
"""
Патч main.py:
1. Добавляет npm/JS-пакеты в DEFAULT_RULES
2. Учит парсер отличать лицензию от версии
3. Делает backup + проверку синтаксиса
"""
import shutil
import sys
import os

MAIN_FILE = "main.py"
BACKUP_FILE = "main.py.bak"


def backup():
    if not os.path.exists(MAIN_FILE):
        print(f"❌ Файл {MAIN_FILE} не найден")
        sys.exit(1)
    shutil.copy2(MAIN_FILE, BACKUP_FILE)
    print(f"✅ Резервная копия: {BACKUP_FILE}")


def patch_rules(content: str) -> tuple:
    """Добавляет npm-пакеты после 'pytest'."""
    anchor = '''    "pytest": {"license": "MIT", "status": "Разрешено", "recommendation": "pytest."},
}'''

    npm_block = '''    "pytest": {"license": "MIT", "status": "Разрешено", "recommendation": "pytest."},

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
}'''

    if anchor in content:
        content = content.replace(anchor, npm_block, 1)
        print("✅ Патч 1: npm/JS + Java-правила добавлены")
        return content, True
    else:
        print("⚠️ Патч 1: якорь 'pytest + }' не найден")
        return content, False


def patch_version_parser(content: str) -> tuple:
    """Добавляет функцию _is_license_like и вызывает её в parse_uploaded_file."""
    # 1. Добавляем функцию-хелпер перед parse_uploaded_file
    helper_anchor = "def parse_uploaded_file(file_bytes: bytes, filename: str) -> list:"
    helper_code = '''def _is_license_like(text: str) -> bool:
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


def parse_uploaded_file(file_bytes: bytes, filename: str) -> list:'''

    if helper_anchor in content:
        content = content.replace(helper_anchor, helper_code, 1)
        print("✅ Патч 2.1: функция _is_license_like добавлена")
    else:
        print("⚠️ Патч 2.1: якорь parse_uploaded_file не найден")
        return content, False

    # 2. Нормализация версий после парсинга
    norm_anchor = '''    except Exception as e:
        print(f"Parse error {filename}: {e}")
    if not extracted:
        extracted = [{"name": filename.split(".")[0], "version": "1.0.0"}]
    return extracted'''

    norm_code = '''    except Exception as e:
        print(f"Parse error {filename}: {e}")
    # Нормализация: если "версия" на самом деле лицензия — сбрасываем
    for item in extracted:
        if _is_license_like(item.get("version", "")):
            item["version"] = "unknown"
    if not extracted:
        extracted = [{"name": filename.split(".")[0], "version": "1.0.0"}]
    return extracted'''

    if norm_anchor in content:
        content = content.replace(norm_anchor, norm_code, 1)
        print("✅ Патч 2.2: нормализация версий добавлена")
        return content, True
    else:
        print("⚠️ Патч 2.2: якорь нормализации не найден")
        return content, False


def verify_syntax():
    print("\n🔍 Проверка синтаксиса...")
    result = os.system("python3 -m py_compile main.py")
    if result == 0:
        print("✅ Синтаксис корректен")
        return True
    print("❌ Ошибка синтаксиса! Восстанавливаем из backup...")
    shutil.copy2(BACKUP_FILE, MAIN_FILE)
    print("✅ Файл восстановлен")
    return False


if __name__ == "__main__":
    print("=" * 55)
    print("🔧 Патч npm + парсера версий для main.py")
    print("=" * 55)

    backup()

    with open(MAIN_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    content, ok1 = patch_rules(content)
    content, ok2 = patch_version_parser(content)

    if not (ok1 or ok2):
        print("\n❌ Ни один патч не применён. Восстановить из backup?")
        if input("(y/n): ").strip().lower() == "y":
            shutil.copy2(BACKUP_FILE, MAIN_FILE)
            print("✅ Восстановлено")
        sys.exit(1)

    with open(MAIN_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    if not verify_syntax():
        sys.exit(1)

    print("\n🎉 Патч применён! Пересоберите контейнер:")
    print("   docker compose down -v && docker compose up -d --build")
