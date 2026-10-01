import re

def norm(s):
    """Базовая нормализация строки: нижний регистр, удаление кавычек, ё->е, схлопывание пробелов + специфичные замены для закусок."""
    s = str(s).strip().lower().replace('ё', 'е').replace('"', '').replace("'", '')
    s = re.sub(r'\bпятачк', 'пяточк', s)
    s = re.sub(r'\bвял\b|\bвял\.', 'вяленый', s)
    s = re.sub(r'\bсуш\b|\bсуш\.', 'сушеный', s)
    s = re.sub(r'суш[- ]?коп\w*', 'сушеный копченый', s)
    s = re.sub(r'\bх/?к\b', 'холодного копчения', s)
    s = re.sub(r'\bг/?к\b', 'горячего копчения', s)
    s = re.sub(r'\bсо\s+вкусом\b|\bсо\s+вк\b|\bс\s+ароматом\b|\bвкус\b|\bсо\b', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def clean_snack_name(name):
    """Унификация граммовок: '(75 г)' -> '75г', '75 г' -> '75г', '75гр' -> '75г'."""
    s = str(name)
    s = re.sub(r'\(\s*(\d+)\s*(?:г|гр)\.?\s*\)', r'\1г', s, flags=re.I)
    s = re.sub(r'(\d+)\s*(?:г|гр)\.?\b', r'\1г', s, flags=re.I)
    return re.sub(r'\s+', ' ', s).strip()

def get_tokens(s):
    """Разбиение на токены с удалением стоп-слов для нечеткого поиска."""
    cleaned = re.sub(r'[^a-zа-я0-9\s]', ' ', norm(s))
    tokens = cleaned.split()
    stops = {'в', 'и', 'на', 'с', 'гр', 'г', 'вес', 'п', 'ооо', 'вк', 'штук', 'шт', 'для'}
    return [t for t in tokens if t not in stops and len(t) > 1]