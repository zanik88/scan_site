#!/usr/bin/env python3
"""
Патч №4: исправление _detect_category.
- Переставляет СУБД перед игровыми движками
- Заменяет нечёткое 'in' на regex с границами слов
"""
import shutil
import sys
import os

MAIN_FILE = "main.py"
BACKUP_FILE = "main.py.bak4"


def backup():
    if not os.path.exists(MAIN_FILE):
        print(f"❌ Файл {MAIN_FILE} не найден")
        sys.exit(1)
    shutil.copy2(MAIN_FILE, BACKUP_FILE)
    print(f"✅ Резервная копия: {BACKUP_FILE}")


def patch(content: str) -> tuple:
    """Переносит СУБД перед игровыми движками и уточняет regex."""
    old_block = '''    if any(k in n for k in ["unity", "unreal", "godot", "cryengine"]):
        return "Игровые движки"

    if any(k in n for k in ["aws", "azure", "google", "firebase", "amazon web services", "yandex cloud", "sbercloud"]):
        return "Облачные сервисы"

    if any(k in n for k in ["docker", "kubernetes", "k8s", "containerd", "podman", "helm",
                             "kustomize", "openshift", "rancher", "istio", "envoy", "etcd", "traefik"]):
        return "Контейнеризация и оркестрация"

    os_keys = ["windows", "linux", "ubuntu", "debian", "centos", "red hat", "rhel", "fedora",
               "suse", "alpine", "astra", "alt linux", "ред ос", "red os", "роса", "rosa",
               "macos", "freebsd", "openbsd", "gentoo", "almalinux", "rocky", "opensuse",
               "slackware", "mandriva", "mint", "busybox", "systemd", "glibc", "gnu bash", "bash"]
    if any(k in n for k in os_keys):
        return "Операционные системы"

    db_keys = ["postgres", "mysql", "mariadb", "oracle", "sql server", "sqlite", "mongodb",
               "redis", "valkey", "clickhouse", "cassandra", "scylladb", "couchdb", "neo4j",
               "elasticsearch", "opensearch", "kafka", "rabbitmq", "zookeeper", "influxdb",
               "sap hana", "enterprisedb", "npgsql", "boto3", "botocore", "s3transfer",
               "devart", "db2", "teradata"]
    if any(k in n for k in db_keys):
        return "СУБД и хранилища"'''

    new_block = '''    # ВАЖНО: СУБД проверяем РАНЬШЕ игровых движков, чтобы "community" не
    # попадало под "unity". Используем границы слов через regex.
    def _has_word(text, word):
        return re.search(r'\\b' + re.escape(word) + r'\\b', text) is not None

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
        return "Операционные системы"'''

    if old_block in content:
        content = content.replace(old_block, new_block, 1)
        print("✅ Патч: переставлены СУБД, ОС, игровые движки + regex с границами слов")
        return content, True
    print("⚠️ Якорь _detect_category не найден.")
    return content, False


def verify():
    print("\n🔍 Проверка синтаксиса...")
    if os.system("python3 -m py_compile main.py") == 0:
        print("✅ Синтаксис корректен")
        return True
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BACKUP_FILE, MAIN_FILE)
    return False


if __name__ == "__main__":
    print("=" * 60)
    print("🔧 Патч №4: исправление _detect_category")
    print("=" * 60)
    backup()
    with open(MAIN_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    content, ok = patch(content)
    if not ok:
        if input("Восстановить? (y/n): ").strip().lower() == "y":
            shutil.copy2(BACKUP_FILE, MAIN_FILE)
        sys.exit(1)
    with open(MAIN_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    if not verify():
        sys.exit(1)
    print("\n🎉 Готово! Пересоберите контейнер:")
    print("   docker compose down && docker compose up -d --build")
