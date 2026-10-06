#!/usr/bin/env python3
"""
Нормализация базы знаний ассортимента ПК "Канцлеръ".
Читает xlsx, исправляет опечатки, добавляет категории и chunk_text.

Использование:
    python normalize_beer_kb.py <input.xlsx> [output.csv]

Особенности:
- Строка заголовков определяется автоматически (первая строка листа,
  содержащая ячейку "Название продукта"), номер строки не хардкодится.
- Исправляются опечатки исходного файла.
- Унифицируется формат фильтрации: "да/нет" -> "опционально".
- Добавляется колонка "Категория" (маппинг по стилю).
- Добавляется колонка "chunk_text" — готовый текст чанка для Dify Knowledge Base.
"""

import re
import sys

import pandas as pd

# Маппинг стилей на категории (ключи — в нижнем регистре, сравнение нормализованное)
STYLE_TO_CATEGORY = {
    'светлый лагер': 'лагер',
    'темный лагер': 'лагер',
    'лагер': 'лагер',
    'пилснер': 'лагер',
    'светлый лагер (келлербир)': 'лагер',
    'чешский премиум-лагер': 'лагер',
    'пшеничный лагер': 'лагер',
    'пейл эль': 'эль',
    'вишневый эль': 'эль',
    'вайсбир американский стиль (пшеничное пиво)': 'пшеничное',
    'бельгийский витбир (пшеничное пиво)': 'пшеничное',
    'витбир': 'пшеничное',
    'лагер (пшеничное пиво)': 'пшеничное',
    'стаут': 'стаут',
    'русский имперский стаут': 'стаут',
    'портер': 'портер',
    'пивной напиток': 'пивной_напиток',
    'квас': 'безалкогольное',
    'лимонад': 'безалкогольное',
}

# Опечатки, исправляемые регулярными выражениями (см. fix_typos):
#   - "элевые дрожи"       -> "элевые дрожжи"
#   - "Редкиого"/"Русскиого имперского" -> "Русского" (файл содержит вариант "Русскиого")
#   - "гормоничная"        -> "гармоничная"
#   - изолированное "пите" -> "питкое"
#   - "витбиров"           -> "витбир" (кроме корректного род. падежа мн. ч. "бельгийских витбиров")
#   - "чувствется"         -> "чувствуется"
#   - "на ряду"            -> "наряду"
TYPO_FIXES = {
    'элевые дрожи': 'элевые дрожжи',
    'Редкиого': 'Русского',
    'гормоничная': 'гармоничная',
    'пите': 'питкое',
    'витбиров': 'витбир',
}


def find_header_row(xl, sheet_name='Главное'):
    """Автоматически определяет номер строки с заголовками.

    Возвращает индекс строки (0-based), содержащей ячейку "Название продукта".
    """
    raw = pd.read_excel(xl, sheet_name=sheet_name, header=None)
    for i in range(len(raw)):
        if any('Название продукта' in str(v) for v in raw.iloc[i].tolist()):
            return i
    raise ValueError("Не найдена строка с заголовком 'Название продукта'")


def detect_shifted_columns(df):
    """Определяет и исправляет смещение данных относительно заголовков.

    В исходном xlsx в позиции "Овсяный стаут" (лист "Главное") пропущена
    пустая ячейка "Содержание алкоголя %", из-за чего значения столбцов
    [Фильтрация, IBU] сдвинуты на один столбец влево:
      - в "Фильтрация" стоит крепость 4.7 (% об.);
      - в "IBU" стоит настоящее значение IBU (25);
      - настоящая фильтрация ("нет") потеряна; "Форма выпуска" при этом
        осталась на месте.

    Признаки сдвига:
      1) числовое значение в столбце "Фильтрация" (там должны быть только
         "да"/"нет"/"да/нет");
      2) корректное целочисленное значение в столбце "IBU";
      3) корректная строка в столбце "Форма выпуска".

    Для таких строк число из "Фильтрация" переносится в
    "Содержание алкоголя %", "Фильтрация" становится "не указано",
    "IBU" остаётся без изменений.

    Возвращает список индексов исправленных строк.
    """
    shifted = []
    for idx, row in df.iterrows():
        filt, ibu, form = row['Фильтрация'], row['IBU'], row['Форма выпуска']
        num_filt = False
        if pd.notna(filt):
            try:
                float(str(filt).replace(',', '.'))
                num_filt = True
            except ValueError:
                pass
        ibu_ok = pd.notna(ibu) and isinstance(ibu, (int, float))
        form_ok = isinstance(form, str) and ('Розлив' in form or 'Бутылочное' in form)
        if num_filt and ibu_ok and form_ok:
            df.at[idx, 'Содержание алкоголя %'] = filt   # крепость лежала в "Фильтрация"
            df.at[idx, 'Фильтрация'] = None              # настоящее значение в источнике потеряно
            shifted.append(idx)
    return shifted


def normalize_filter(value):
    """Унифицирует формат фильтрации: да/нет -> опционально."""
    if pd.isna(value):
        return 'не указано'
    value = str(value).strip().lower()
    if value == 'да/нет':
        return 'опционально'
    return value


def fix_typos(text):
    """Исправляет опечатки в тексте."""
    if pd.isna(text):
        return text
    text = str(text)
    # "Русскиого имперского" -> "Русского имперского" (фактический вариант)
    text = re.sub(r'Р[её]дк[ио]ого\s+имперского', 'Русского имперского', text)
    text = text.replace('Русскиого', 'Русского')
    text = text.replace('Редкиого', 'Русского')
    # "элевые дрожи"/артефакт "дрожжии" -> "дрожжи".
    # NB: \b в Python не работает с кириллицей — обрамляем через (?<!\w)/(?!\w).
    # Корректные формы ("дрожжи", "дрожжей", "дрожжевых", "дрожжами") не трогаем.
    text = re.sub(r'(?<!\w)(?:дрожи|дрожжии)(?!\w)', 'дрожжи', text)
    # "гормоничная" -> "гармоничная"
    text = re.sub(r'гор+мон(ичн|ящ)', r'гармон\1', text)
    # изолированное "пите" -> "питкое" (\b не работает с кириллицей)
    text = re.sub(r'(?<!\w)пите(?!\w)', 'питкое', text)
    # "витбиров" -> "витбир" только там, где это грамматически уместно
    # (исключение: корректный род. падеж мн. ч. "бельгийских витбиров" не трогаем)
    text = re.sub(r'(?<!бельгийских )витбиров', 'витбир', text)
    # прочие мелкие опечатки
    text = text.replace('чувствется', 'чувствуется')
    text = text.replace('на ряду', 'наряду')
    text = re.sub(r'(?<!\w)предумали(?!\w)', 'придумали', text)
    text = text.replace('выреженный', 'выраженный')
    # схлопывание прострелов (2+ горизонтальных пробела/nbsp -> один), переводы строк сохраняем
    text = re.sub(r'[^\S\n]{2,}', ' ', text)
    return text


def normalize_style(style):
    """Нормализует строку стиля для маппинга на категорию."""
    if pd.isna(style):
        return ''
    s = str(style).strip().lower()
    s = re.sub(r'\s+', ' ', s)
    return s


def parse_abv(value):
    """Пытается извлечь числовое значение крепости (% об.); None если не число."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    m = re.search(r'\d+[.,]?\d*', str(value))
    if not m:
        return None
    try:
        return float(m.group().replace(',', '.'))
    except ValueError:
        return None


def map_category(style, abv=None):
    """Возвращает категорию по стилю.

    Приоритетное правило: если крепость <= 0.5 % об. — категория
    «безалкогольное» (независимо от стиля).
    """
    if abv is not None and abv <= 0.5:
        return 'безалкогольное'
    s = normalize_style(style)
    if s in STYLE_TO_CATEGORY:
        return STYLE_TO_CATEGORY[s]
    # резервные правила
    if 'напиток' in s:
        return 'пивной_напиток'
    if 'квас' in s or 'лимонад' in s or 'безалко' in s:
        return 'безалкогольное'
    if 'стаут' in s:
        return 'стаут'
    if 'портер' in s:
        return 'портер'
    if 'эль' in s:
        return 'эль'
    if 'витбир' in s or 'вайсбир' in s or 'пшеничное пиво' in s:
        return 'пшеничное'
    if 'лагер' in s or 'пилснер' in s:
        return 'лагер'
    return 'неизвестно'


def clean_value(value, empty_text='не указано'):
    """Приводит значение к строке без 'nan'; пустое -> empty_text."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return empty_text
    s = str(value).strip()
    if s == '' or s.lower() == 'nan':
        return empty_text
    return s


def format_number(value):
    """Форматирует число: 25.0 -> 25, '11\\12' -> '11/12', nan -> 'не указано'."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 'не указано'
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = str(value).strip().replace('\\', '/').replace('/', '/')
    return s if s else 'не указано'


# ---------------------------------------------------------------------------
# Ключевые слова (теги) для улучшения retrieval в Dify (hybrid search).
# Теги добавляются в конец каждого chunk_text строкой
# "Ключевые слова для поиска: ..." — они усиливают и векторный, и
# ключевой (BM25-подобный) поиск. Внутри самого чанка разделитель секций
# остаётся "\n\n", поэтому между блоками в *.txt выгрузке можно использовать
# уникальный разделитель "\n\n===\n\n".
# ---------------------------------------------------------------------------

# Ручные теги по названию позиции (подстрока -> теги). Регистронезависимо.
NAME_TAGS = {
    'овсяный стаут': 'стаут овсяное oatmeal stout сливочное кофейное карамельное темное плотное',
    'боровское темное': 'лагер темное тёмное dark lager хлебное солодовое',
    'боровское белое': 'пшеничное вайсбир wheat нефильтрованное бананово-гвоздичное лёгкое освежающее',
    'вайс канцлеръ': 'вайсбир пшеничное weizen нефильтрованное банан гвоздика лёгкое освежающее',
    'бельгийское': 'витбир witbier пшеничное бельгийское кориандр цедра лёгкое мягкое',
    'белый кролик': 'витбир witbier пшеничное бельгийское цедра кориандр лёгкое мягкое',
    'wild cherry': 'эль вишневый fruit cherry beer сладкое фруктовое десертное розовое',
    'хмельзила': 'ipa индийский пейл эль indian pale ale горькое крафтовое ароматное хмелевое',
    'бирконг': 'apa american pale ale пейл эль американское горькое цитрусовое крафтовое',
    'обер канцлеръ': 'келлербир затур лагер нефильтрованное мутное классическое баварское',
    'бундес канцлеръ': 'лагер светлое классическое немецкое питкое мягкое',
    'вице канцлеръ': 'безалкогольное безалко 0% non-alcoholic alcohol-free лагер светлое',
    'жигулевское': 'лагер светлое классическое советское традиционное питкое мягкое',
    'пилснер': 'лагер пилснер pilsner чешское светлое сухое питкое',
    'чешское': 'лагер светлое чешское классическое питкое мягкое',
    'заправское': 'лагер светлое чешское классическое питкое мягкое',
    'бирховен': 'лагер светлое классическое питкое мягкое',
    'империал канцлеръ': 'лагер крепкое strong export плотное насыщенное',
    'viva шампань': 'пивной напиток шампань игристое сладкое фруктовое коктейльное',
    'viva пина-кола': 'пивной напиток пина-кола кокос тропики ананас сладкое коктейльное',
    'viva мохито': 'пивной напиток мохито лайм мята освежающее коктейльное',
    'квас заквас': 'квас безалкогольное безалко 0% bread drink квасной хлебный русский',
    'лимонадный джо': 'лимонад безалкогольное безалко 0% lemonade soda лимон апельсиновое газированное',
    'блэкаут': 'рис imperial stout русский имперский стаут плотное крепкое десертное кофейное шоколадное',
    'лорд канцлеръ': 'портер porter тёмное темное кофейно-шоколадное карамельное',
    'бархатное': 'лагер тёмное темное dark lager бархатистое карамельное мягкое',
    'ceska koruna': 'лагер пилснер чешский premium bohemian pilsner светлое',
    'weizen': 'вайсбир вайцен пшеничное weizen hefeweizen банан гвоздика светлое',
    'svetle': 'светлый светлое пилснер pilsner чешский czech lager svickov',
    'desitka': 'десятка ten svoboda чешский лагер светлое лёгкое питкое',
    'дипломат': 'лагер светлое классическое чешское питкое',
    'хадыженское': 'лагер светлое классическое кавказское питкое мягкое',
}

# Общие теги по категории (дополняются всегда).
CATEGORY_TAGS = {
    'лагер': 'лагер lager',
    'эль': 'эль ale',
    'пшеничное': 'пшеничное weizen wheat',
    'стаут': 'стаут stout',
    'портер': 'портер porter',
    'пивной_напиток': 'пивной напиток cocktail',
    'безалкогольное': 'безалкогольное безалко 0% non-alcoholic alcohol-free',
}


def parse_ibu(value):
    """Извлекает первое число IBU; None если значения нет."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    m = re.search(r'\d+', str(value))
    return int(m.group()) if m else None


def taste_tags(row):
    """Характеристики словами (горькое/мягкое/лёгкое/плотное...) по IBU,
    крепости, плотности и органолептике."""
    tags = []
    ibu = parse_ibu(row.get('IBU'))
    abv = parse_abv(row.get('Содержание алкоголя %'))
    og = parse_abv(row.get('Плотность %'))

    # Горечь: явный диапазон IBU + подстраховка по тексту (для позиций без IBU)
    text = ' '.join(str(row[c]) for c in [
        'Краткое описание органолептики продукта',
        'Полное описание органолептики продукта и с чем данный продукт сочетается',
        'Дополнительная информация'] if pd.notna(row.get(c))).lower()
    soft_bitter = bool(re.search(r'мягч|легк|лёгк.{0,30}горчин|слаб.{0,15}горчин|небольш.{0,15}горчин|питк', text))

    if ibu is not None:
        if ibu >= 30:
            tags.append('горькое')
        elif ibu >= 15:
            tags.append('умеренная горечь')
        else:
            tags.append('мягкое')
    elif soft_bitter:
        tags.append('мягкое')

    if abv is not None:
        if abv == 0 or abv <= 0.5:
            tags.append('безалкогольное')
        elif abv <= 4.6:
            tags.append('лёгкое')
        elif abv >= 7:
            tags.append('крепкое')

    if og is not None and og >= 16:
        tags.append('плотное')

    if re.search(r'освеж', text):
        tags.append('освежающее')
    if re.search(r'сладк', text):
        tags.append('сладкое')
    return tags


def build_search_tags(row):
    """Собирает итоговую строку тегов для chunk_text."""
    name = normalize_style(row['Название продукта'])  # lower + схлопнутые пробелы
    tags = []
    for key, val in NAME_TAGS.items():
        if key in name:
            tags.append(val)
    cat = row.get('Категория')
    if cat in CATEGORY_TAGS:
        tags.append(CATEGORY_TAGS[cat])
    tt = taste_tags(row)
    if tt:
        tags.append(' '.join(tt))
    ibu = parse_ibu(row.get('IBU'))
    if ibu is not None:
        tags.append(f'ibu {ibu}')
    # уникальные слова с сохранением порядка
    seen, uniq = set(), []
    for w in ' '.join(tags).split():
        lw = w.lower()
        if lw not in seen:
            seen.add(lw)
            uniq.append(w)
    return ' '.join(uniq)


def create_chunk_text(row):
    """Создаёт текст чанка для Dify Knowledge Base."""
    ibu = clean_value(format_number(row['IBU']))
    otlichie = clean_value(row['Отличие от конкурентов'])
    dop_info = clean_value(row['Дополнительная информация'])
    plotnost = clean_value(format_number(row['Плотность %']))
    alk = clean_value(row['Содержание алкоголя %'])

    chunk = f"""Позиция: {clean_value(row['Название продукта'])}
Стиль: {clean_value(row['Стиль'])}
Категория: {row['Категория']}
Крепость: {alk} % об.
Плотность: {plotnost} %
IBU: {ibu}
Фильтрация: {row['Фильтрация']}
Форма выпуска: {clean_value(row['Форма выпуска'])}

Рецептура и технология:
{clean_value(row['Свойства'])}

Вкус и аромат (кратко):
{clean_value(row['Краткое описание органолептики продукта'])}

Полное описание и сочетания с едой:
{clean_value(row['Полное описание органолептики продукта и с чем данный продукт сочетается'])}

Отличие от конкурентов:
{otlichie}

Дополнительная информация:
{dop_info}

Ключевые слова для поиска: {build_search_tags(row)}"""
    return chunk


def main():
    if len(sys.argv) < 2:
        print("Использование: python normalize_beer_kb.py <input.xlsx> [output.csv]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.rsplit('.xlsx', 1)[0] + '_normalized.csv'

    xl = pd.ExcelFile(input_file)
    sheet_name = 'Главное' if 'Главное' in xl.sheet_names else xl.sheet_names[0]
    header_row = find_header_row(xl, sheet_name)
    print(f"Лист: {sheet_name!r}, строка заголовков: {header_row} (0-based)")

    df = pd.read_excel(xl, sheet_name=sheet_name, header=header_row)

    # Удаляем пустые строки
    df = df.dropna(subset=['Название продукта']).reset_index(drop=True)

    # Исправляем смещение данных в строках с пропущенными ячейками (обнаруживается автоматически)
    shifted = detect_shifted_columns(df)
    if shifted:
        names = ', '.join(df.loc[i, 'Название продукта'] for i in shifted)
        print(f"   ⚠️ Исправлено смещение колонок в {len(shifted)} строке(ах): {names}")

    # Нормализуем пробелы в названиях/стилях и унифицируем фильтрацию
    df['Название продукта'] = df['Название продукта'].apply(
        lambda v: re.sub(r'\s+', ' ', str(v)).strip())
    df['Стиль'] = df['Стиль'].apply(lambda v: re.sub(r'\s+', ' ', str(v)).strip())
    df['Фильтрация'] = df['Фильтрация'].apply(normalize_filter)

    # Исправляем опечатки во всех текстовых колонках
    text_cols = ['Свойства', 'Краткое описание органолептики продукта',
                 'Полное описание органолептики продукта и с чем данный продукт сочетается',
                 'Отличие от конкурентов', 'Дополнительная информация']
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].apply(fix_typos)

    # Добавляем категорию (приоритет: крепость <= 0.5 -> безалкогольное)
    df['Категория'] = df.apply(
        lambda r: map_category(r['Стиль'], parse_abv(r['Содержание алкоголя %'])), axis=1)

    # Добавляем chunk_text
    df['chunk_text'] = df.apply(create_chunk_text, axis=1)

    # Сохраняем CSV (chunk_text содержит переносы строк, поэтому для txt-выгрузки
    # ниже блоки соединяются уникальным разделителем "\n\n===\n\n")
    df.to_csv(output_file, index=False, encoding='utf-8-sig')

    # Текстовая выгрузка для Dify Knowledge Base (1 позиция = 1 блок).
    # Внутри чанка секции разделены "\n\n", между блоками — "\n\n===\n\n".
    txt_file = output_file.rsplit('.csv', 1)[0] + '_for_dify.txt'
    blocks = [str(t).strip() for t in df['chunk_text']]
    with open(txt_file, 'w', encoding='utf-8') as f:
        f.write('\n\n===\n\n'.join(blocks) + '\n')

    print("✅ Нормализация завершена")
    print(f"   Входной файл: {input_file}")
    print(f"   Выходной файл: {output_file}")
    print(f"   TXT для Dify: {txt_file} (разделитель блоков: \\n\\n===\\n\\n)")
    print(f"   Позиций: {len(df)}")
    print(f"   Категорий: {df['Категория'].nunique()}")
    unknown = df[df['Категория'] == 'неизвестно']
    if len(unknown):
        print("   ⚠️ Не замапленные стили:", sorted(unknown['Стиль'].unique()))


if __name__ == '__main__':
    main()
