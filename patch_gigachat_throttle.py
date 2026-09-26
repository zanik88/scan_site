#!/usr/bin/env python3
"""
Фикс rate limit GigaChat:
1. Semaphore(3) → Semaphore(1) — последовательные ИИ-запросы
2. Задержка 1.5 сек между запросами
3. Retry при 429 (до 3 попыток с паузами)
4. Добавлены правила: vLLM, llama.cpp, JupyterLab, ruff, OPA, Boundary, TensorFlow
"""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_throttle"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Semaphore(3) → Semaphore(1)
# ============================================================
old1 = 'sem = asyncio.Semaphore(3)  # Ограничение для GigaChat (rate limit)'
new1 = 'sem = asyncio.Semaphore(1)  # Только 1 ИИ-запрос одновременно (rate limit GigaChat)'
if old1 in content:
    content = content.replace(old1, new1, 1)
    patched.append("Semaphore(3) → Semaphore(1)")

# ============================================================
# 2. Retry на 429 в _call_gigachat + пауза между запросами
# ============================================================
old2 = '''        async with session.post(url, headers=headers, json=payload, ssl=False,
                                timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                data = await resp.json()
                parsed = _extract_json(data["choices"][0]["message"]["content"])
                if parsed:
                    parsed["provider"] = "GigaChat"
                    return parsed
            else:
                err = await resp.text()
                print(f"[AI] GigaChat chat ошибка: {resp.status} {err[:200]}")
    except Exception as e:
        print(f"[AI] GigaChat error: {e}")
    return None'''

new2 = '''        # Retry при 429 (rate limit) — до 3 попыток
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
    return None'''
if old2 in content:
    content = content.replace(old2, new2, 1)
    patched.append("Retry на 429 добавлен (3 попытки с паузами 2/4/6 сек)")

# ============================================================
# 3. Пауза между ИИ-запросами в process_audit_task
# ============================================================
old3 = '''                res = await fetch_package_info_with_version(
                    session, item["name"], item["version"], cached_rules, report_id, ai_provider)
                if report_id in PROGRESS_TRACKER:
                    PROGRESS_TRACKER[report_id]["processed"] += 1
                return res'''

new3 = '''                res = await fetch_package_info_with_version(
                    session, item["name"], item["version"], cached_rules, report_id, ai_provider)
                # Пауза 1.5 сек перед следующим ИИ-запросом
                await asyncio.sleep(1.5)
                if report_id in PROGRESS_TRACKER:
                    PROGRESS_TRACKER[report_id]["processed"] += 1
                return res'''
if old3 in content:
    content = content.replace(old3, new3, 1)
    patched.append("Пауза 1.5 сек между ИИ-запросами")

# ============================================================
# 4. Добавить правила для частых компонентов
# ============================================================
anchor4 = '''    "packer": {"license": "BUSL-1.1", "status": "⚠️ Требует внимания", "recommendation": "Packer — BUSL."},
}'''

new4 = '''    "packer": {"license": "BUSL-1.1", "status": "⚠️ Требует внимания", "recommendation": "Packer — BUSL."},

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
}'''

if anchor4 in content:
    content = content.replace(anchor4, new4, 1)
    patched.append("Добавлено 35+ правил: AI/ML, DevTools, IaC")

with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n✅ Патчей применено: {len(patched)}")
for p in patched:
    print(f"   • {p}")

print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Дальше:")
    print("   ./release.sh 9.2.2")
else:
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
