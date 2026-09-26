#!/usr/bin/env python3
"""Добавляет популярные DevTools, языки и ML-библиотеки в DEFAULT_RULES."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_devtools"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

# Настоящий якорь — последняя запись DEFAULT_RULES
anchor = '''    "aws-sdk-php": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "AWS SDK for PHP. Замена: MinIO SDK."},
}'''

new_block = '''    "aws-sdk-php": {"license": "Apache-2.0", "status": "❌ Запрещено", "recommendation": "AWS SDK for PHP. Замена: MinIO SDK."},

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
}'''

if anchor in content:
    content = content.replace(anchor, new_block, 1)
    print("✅ Добавлено 80+ правил для популярных DevTools, языков и ML-библиотек")
else:
    print("❌ Якорь 'aws-sdk-php' не найден.")
    sys.exit(1)

# ============================================================
# Уменьшить параллелизм ИИ, чтобы не упираться в rate limit GigaChat
# ============================================================
old_conc = 'sem = asyncio.Semaphore(10)'
new_conc = 'sem = asyncio.Semaphore(3)  # Ограничение для GigaChat (rate limit)'

if old_conc in content:
    content = content.replace(old_conc, new_conc, 1)
    print("✅ Параллелизм ИИ-запросов снижен с 10 до 3")

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Дальше:")
    print("   ./release.sh 9.2.0")
else:
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
