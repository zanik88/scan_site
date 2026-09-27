#!/usr/bin/env python3
"""Добавляет кнопку отмены проверки на странице прогресса."""
import shutil, os, sys

MAIN = "main.py"
BAK = "main.py.bak_cancel"

shutil.copy2(MAIN, BAK)
print(f"✅ Backup: {BAK}")

with open(MAIN, "r", encoding="utf-8") as f:
    content = f.read()

patched = []

# ============================================================
# 1. Заменить полностью функцию audit_progress_page
# ============================================================
old_func = '''async def audit_progress_page(report_id: int):
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
    """)'''

new_func = '''async def audit_progress_page(report_id: int):
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
                const pct = Math.round((d.processed/d.total)*100);
                document.getElementById('pf').style.width = pct + '%';
                document.getElementById('pt').innerText = `Анализ: ${{d.processed}}/${{d.total}} (${{pct}}%)`;
            }}
            if(d.status==='completed') window.location.href='/audit/{report_id}/result';
            else if(d.status==='failed'){{alert('Ошибка анализа');window.location.href='/';}}
            else if(d.status==='cancelled' || d.status==='deleted'){{window.location.href='/';}}
            else setTimeout(check,1000);
        }}catch(e){{setTimeout(check,2000);}}
    }} check();
    </script></body></html>
    """)'''

if old_func in content:
    content = content.replace(old_func, new_func, 1)
    patched.append("Страница прогресса с кнопкой отмены")
else:
    print("❌ Старая функция audit_progress_page не найдена")

# ============================================================
# 2. Добавить эндпоинт /audit/{id}/cancel перед get_audit_status
# ============================================================
anchor = '''@app.get("/audit/{report_id}/status")'''
cancel_endpoint = '''@app.post("/audit/{report_id}/cancel")
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


@app.get("/audit/{report_id}/status")'''

if "async def cancel_audit" not in content and anchor in content:
    content = content.replace(anchor, cancel_endpoint, 1)
    patched.append("Эндпоинт /audit/{id}/cancel")
else:
    print("⚠️ Эндпоинт отмены уже есть или якорь не найден")

# ============================================================
# 3. В process_audit_task — пометить отчёт как cancelled при отмене
# ============================================================
old_cancel = '''            if PROGRESS_TRACKER.get(report_id, {}).get("cancel", False):
                rep = db.query(AuditReport).filter(AuditReport.id == report_id).first()
                if rep:
                    db.delete(rep)
                    db.commit()
                return'''

new_cancel = '''            if PROGRESS_TRACKER.get(report_id, {}).get("cancel", False):
                rep = db.query(AuditReport).filter(AuditReport.id == report_id).first()
                if rep:
                    rep.status = "cancelled"
                    db.commit()
                    print(f"[CANCEL] Отчёт #{report_id} помечен как cancelled")
                return'''

if old_cancel in content:
    content = content.replace(old_cancel, new_cancel, 1)
    patched.append("Обработка отмены в process_audit_task")

# ============================================================
# Записать
# ============================================================
with open(MAIN, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n✅ Патчей применено: {len(patched)}")
for p in patched:
    print(f"   • {p}")

print("\n🔍 Проверка синтаксиса...")
if os.system("python3 -m py_compile main.py") == 0:
    print("✅ Синтаксис корректен")
    print("\n🎉 Готово! Дальше:")
    print("   ./release.sh 9.3.0")
else:
    print("❌ Ошибка! Восстанавливаем...")
    shutil.copy2(BAK, MAIN)
    sys.exit(1)
