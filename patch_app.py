with open("app.py", "r", encoding="utf-8") as f:
    text = f.read()

# Вариант 1: обычный перенос
old_str_1 = '" Excel</a></td></tr>"'
# Вариант 2: слитная строка
old_str_2 = '<td><a href=\'/download_excel/{r.excel_filename}\'>Скачать Excel</a></td></tr>'

new_td = '<td><form method="POST" action="/reports/delete/\' + str(r.id) + \'" onsubmit="return confirm(\\\'Удалить эту запись?\\\');" style="margin:0;"><button type="submit" style="background:none;border:none;color:#e74c3c;cursor:pointer;font-weight:bold;text-decoration:underline;">Удалить</button></form></td>'

rep_1 = '" Excel</a></td>" + (' + repr(new_td) + ' if is_admin else "") + "</tr>"'
rep_2 = '<td><a href=\'/download_excel/{r.excel_filename}\'>Скачать Excel</a></td>" + (' + repr(new_td) + ' if is_admin else "") + "</tr>'

if old_str_1 in text:
    text = text.replace(old_str_1, rep_1, 1)
    print("Замена по шаблону 1 выполнена!")
elif old_str_2 in text:
    text = text.replace(old_str_2, rep_2, 1)
    print("Замена по шаблону 2 выполнена!")
else:
    print("Шаблон строки не найден")

with open("app.py", "w", encoding="utf-8") as f:
    f.write(text)
