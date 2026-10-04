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

def _canonicalize_beer_base(name):
    """Старая канонизация пива (без изменений). Переименована для обёртки FIX-05."""
    raw = str(name).strip()
    s = raw.lower().replace('ё', 'е').replace('"', '').replace("'", '')
    if 'жигулевское ссср' in s or ('жигулевск' in s and 'ссср' in s): return 'Жигулевское СССР'
    if 'жигулевское самара' in s or ('жигулевск' in s and 'самар' in s): return 'Жигулевское Самара'
    if 'бельгийск' in s: return 'Бельгийское белое'
    if 'вайцен' in s: return 'Вайцен'
    if 'американский светлый эль' in s or 'бирконг' in s or ' апа' in s or s.startswith('апа'): return 'Бирконг АПА'
    if 'обер' in s: return 'Обер'
    if 'хмельзилл' in s: return 'Хмельзилла'
    if 'варим сусло' in s: return 'Варим сусло'
    if 'вайс' in s and 'вайцен' not in s: return 'Вайс'
    if 'хадыжен' in s: return 'Хадыженское'
    if 'апшерон' in s: return 'Апшеронское'
    if 'корун' in s or 'чешская корона' in s: return 'Чешская корона'
    if 'белый бим' in s: return 'Белый Бим'
    if 'белый кролик' in s: return 'Белый кролик'
    if 'два бобра' in s: return 'Два Бобра'
    if 'блэкаут' in s: return 'Блэкаут'
    if 'томатный гозе' in s: return 'Томатный Гозе'
    if 'пина колада' in s or 'пина - колада' in s: return 'Пина Колада'
    if 'шампань роуз' in s: return 'Шампань Роуз'
    if 'оскар' in s: return 'Оскар'
    if 'лимонад канцлер' in s: return 'Лимонад Канцлер'
    if 'канцлер 0' in s or 'безалкогольн' in s: return 'Канцлер "0" Безалкогольное'
    if 'квас белый' in s: return 'Квас белый'
    if s.startswith('квас'): return 'Квас'

    is_nf = bool(re.search(r'\bнф\b|нефильтр|н/ф', s))
    is_dark, is_white, base_name = 'темн' in s, 'бел' in s and 'баланс' not in s, None

    if 'чешск' in s: base_name = 'Чешское'
    elif 'жигулевск' in s: base_name = 'Жигулевское'
    elif 'заправск' in s: base_name = 'Заправское'
    elif 'боровск' in s: base_name = 'Боровское'
    elif 'восьмидесят' in s: base_name = 'Восьмидесятые'
    elif 'бундес' in s: base_name = 'Бундес'
    elif 'империал' in s: base_name = 'Империал'
    elif 'лазаревск' in s: base_name = 'Лазаревское'
    elif 'всесоюзн' in s: base_name = 'Всесоюзное'
    elif 'бархатн' in s: base_name = 'Бархатное'
    elif 'баланс бел' in s: base_name = 'Баланс Белого'
    elif 'лорд' in s: base_name = 'Лорд'
    elif 'райт' in s: base_name = 'Райт'
    elif 'збитень' in s: base_name = 'Збитень'
    elif 'рижск' in s: base_name = 'Рижское'
    elif 'ейск' in s: base_name = 'Ейское'
    elif 'кардымовск' in s: base_name = 'Кардымовское'
    elif 'бирховен' in s: base_name = 'Бирховен'

    if base_name:
        if is_white: return f'{base_name} белое (н/ф)' if is_nf else f'{base_name} белое'
        if is_dark: return f'{base_name} темное'
        if is_nf: return f'{base_name} (н/ф)'
        return f'{base_name} (ф)'
    return re.sub(r',?\s*(пиво|пивной напиток|медовуха|светлое|темное|непастеризованное|пастеризованное|фильтрованное|нефильтрованное|\d+%|\d+,\d+%).*', '', raw, flags=re.I).strip().strip(' ,"\'-')

def canonicalize_sku(name):
    """Сквозная нормализация названий для объединения одинаковых товаров из G1 и G2"""
    raw = str(name).strip()
    s = norm(raw)

    # 1. Мясные чипсы и карпаччо
    if 'чипсы мясные' in s or 'чипсы сыровяленые' in s:
        if 'свинин' in s:
            if 'корейк' in s: return 'Чипсы мясные свиные "Корейка" (вес)'
            return 'Чипсы мясные свинина 75г'
        if 'куриц' in s or 'курин' in s:
            if 'карпаччо' in s: return 'Чипсы мясные курица "Карпаччо"'
            return 'Чипсы мясные курица 75г'
    if 'карпаччо' in s:
        return 'Чипсы мясные курица "Карпаччо"'

    # 2. Орехи
    if 'фисташк' in s:
        return 'Фисташка жареная соленая'
    if s.startswith('арахис') or s.startswith('ядра арахиса'):
        # Убираем граммовки и скобки
        cleaned = re.sub(r'\(.*?\)', '', raw).strip()
        cleaned = re.sub(r'\b(ядра арахиса|арахис крупный|арахис жареный)\b', 'Арахис', cleaned, flags=re.I)
        return re.sub(r'\s+', ' ', cleaned).strip()

    # 3. Сыры
    if 'сыр нити' in s or s.startswith('нити'):
        flavour = ''
        if 'копчен' in s: flavour = ' копченый'
        elif 'укроп' in s: flavour = ' с укропом'
        elif 'чеснок' in s: flavour = ' с чесноком'
        elif 'паприк' in s or 'чили' in s: flavour = ' паприка и чили'
        elif 'икра' in s: flavour = ' красная икра'
        elif 'аджик' in s: flavour = ' аджика'
        return f'Сыр Нити{flavour} (вес)'

    if 'балыковый' in s:
        if 'карандаш' in s: return 'Сыр Балыковый копчёный (Карандаш)'
        if 'патрон' in s: return 'Сыр Балыковый копчёный (Патрон)'

    # Унификация фасовки в граммах: (75 г) -> 75г, 75 гр -> 75г
    res = re.sub(r'\(\s*(\d+)\s*г\s*\)', r'\1г', raw, flags=re.I)
    res = re.sub(r'(\d+)\s+г\b', r'\1г', res, flags=re.I)
    res = re.sub(r'(\d+)\s*гр\b', r'\1г', res, flags=re.I)
    return re.sub(r'\s+', ' ', res).strip()

# ===== FIX-05: согласованные правила нормализации разливного пива =====
# Замены применяются ТОЛЬКО к каноническому имени точным совпадением (без регистра).
# Поэтому «Морава Деситка 0.5л» (стекло) не затрагивается: её канон — «Морава Деситка 0.5л».
_BEER_CANON_REPLACEMENTS_LOWER = {k.lower(): v for k, v in {
    'Боровское белое (н/ф)': 'Боровское белое',          # правило 1
    'Дипломат': 'Дипломат светлое нф',                   # правило 3
    'Десятка': 'Десятка светлое фильтрованное',          # правило 4
    'Деситка': 'Десятка светлое фильтрованное',          # правило 4 (опечатка)
    'Леди на велосипеде': 'Леди На Велосипеде',          # бонус
    'Леди на велосипеде 0.5л': 'Леди На Велосипеде',     # бонус
}.items()}

def canonicalize_beer(name):
    """Обёртка FIX-05 поверх старой канонизации: исключение Воронежского,
    ранний перехват Октоберфеста (иначе склеится с «Обер» через подстроку),
    затем старая логика и точечные замены канонических имён."""
    s = norm(name)
    if not s:
        return ''
    # Правило 2: фасованное стекло, не разлив — исключаем из анализа
    if 'воронежское' in s and '1978' in s:
        return ''
    # Правило 5: перехват ДО старой логики (баг подстроки 'обер')
    if 'октоберфест' in s:
        return 'Октоберфест фильтрованное'
    res = _canonicalize_beer_base(name)
    return _BEER_CANON_REPLACEMENTS_LOWER.get(res.strip().lower(), res)