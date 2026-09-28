headers = (
    "оглавление", "содержание", "frontend", "backend", "введение",
    "пояснительная", "заключение", "приложение", "раздел", "глава",
    "список", "перечень", "описание", "аннотация", "титульный",
    "table of contents", "contents", "introduction", "conclusion",
    "appendix", "chapter", "section", "list of",
)
if any(lower.startswith(h) for h in headers):
    return True
