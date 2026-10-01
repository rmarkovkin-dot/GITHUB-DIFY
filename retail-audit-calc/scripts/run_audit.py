import argparse, glob, re, os
import pandas as pd
import numpy as np

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=str, default="", help="Категория или ключ поиска")
    args = parser.parse_args()
    target_key = args.target.strip().lower()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def get_path(fname):
        p1 = os.path.join(base_dir, fname)
        if os.path.exists(p1): return p1
        p2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
        if os.path.exists(p2): return p2
        return fname

    sales_p1 = get_path('sales.xlsx')
    sales_p2 = get_path('sales_g2.xlsx')
    cat_p1 = get_path('catalog.xlsx')
    cat_p2 = get_path('catalog_g2.xlsx')

    if not os.path.exists(sales_p1):
        sales_p1 = (glob.glob(os.path.join(base_dir, '*продаж*.xlsx')) or glob.glob('*продаж*.xlsx'))[0]
    if not os.path.exists(cat_p1):
        cat_p1 = (glob.glob(os.path.join(base_dir, '*правочник*.xlsx')) or glob.glob('*правочник*.xlsx'))[0]

    # Чтение продаж (G1)
    sales_df = pd.read_excel(sales_p1, header=1)

    # Добавление продаж (G2: Батова, Родниковая, Штеменко)
    if os.path.exists(sales_p2):
        sales_df2 = pd.read_excel(sales_p2, header=1)
        sales_df = pd.concat([sales_df, sales_df2], ignore_index=True)

    # Чтение каталогов
    cat_frames = []
    if os.path.exists(cat_p1):
        cat_frames.append(pd.read_excel(cat_p1))
    if os.path.exists(cat_p2):
        cat_frames.append(pd.read_excel(cat_p2))
    
    if cat_frames:
        cat_df = pd.concat(cat_frames, ignore_index=True)
    else:
        cat_df = pd.DataFrame(columns=['Наименование', 'Группа товара', 'Единица измерения'])

    sales_df['Наименование'] = sales_df['Наименование'].astype(str).str.strip()
    cat_df['Наименование'] = cat_df['Наименование'].astype(str).str.strip()
    sales_df['МАГАЗИН'] = sales_df['МАГАЗИН'].astype(str).str.strip()
    cat_df['Группа товара'] = cat_df['Группа товара'].astype(str).str.strip()
    cat_df['Единица измерения'] = cat_df['Единица измерения'].astype(str).str.strip().str.lower()

    for c in ['Количество', 'Цена закупки', 'Цена продажи']:
        if c in sales_df.columns:
            sales_df[c] = pd.to_numeric(sales_df[c], errors='coerce').fillna(0)
        else:
            sales_df[c] = 0.0

    def normalize_beer_sku(name: str) -> str:
        s = str(name).lower().replace('ё', 'е').replace('ъ', '')
        if 'пина' in s and 'колад' in s: return "Пина Колада"
        if 'мохито' in s: return "Мохито"
        if 'шампань' in s and 'роуз' in s: return "Шампань Роуз"
        if 'квас' in s: return "Квас"
        if 'лимонад' in s: return "Лимонад Канцлер" if 'канцлер' in s else "Лимонад"
        if 'канцлер' in s and (' 0' in s or 'безалк' in s or '"0"' in s): return 'Канцлер "0" Безалкогольное (ф)'
        if 'белый кролик' in s: return "Белый кролик"
        if 'вайс' in s: return "Вайс (н/ф)"
        if 'блэкаут' in s: return "Блэкаут (ф)"
        if 'варим сусло' in s: return "Варим сусло (ф)"
        if 'апа' in s or 'apa' in s: return "АПА (н/ф)"
        if 'збитень' in s and 'южн' in s: return "Збитень Южный темный с травами"
        if 'бархатн' in s: return "Бархатное темное (ф)"

        is_nf = bool(re.search(r'(\bнф\b|\bн/ф\b|нефильтр)', s))
        is_f  = bool(re.search(r'(\bф\b|\bф/о\b|фильтр)', s)) and not is_nf

        if 'боровск' in s and 'бел' in s: return "Боровское белое (н/ф)"
        filt = " (н/ф)" if is_nf else " (ф)"

        if 'чешск' in s: return f"Чешское{filt}"
        if 'заправск' in s: return f"Заправское{filt}"
        if 'жигулев' in s: return f"Жигулевское{filt}"
        if 'бундес' in s: return f"Бундес{filt}"
        if 'боровск' in s: return f"Боровское{filt}"
        if 'восьмидесят' in s: return f"Восьмидесятые{filt}"

        brands = [
            ('хадыжен', 'Хадыженское'), ('лазаревск', 'Лазаревское'),
            ('всесоюзн', 'Всесоюзное'), ('империал', 'Империал'),
            ('лорд', 'Лорд'), ('апшерон', 'Апшеронское'),
            ('оскар', 'Оскар'), ('райт', 'Райт'),
            ('обер', 'Обер'), ('хмельзилл', 'Хмельзилла'),
            ('белый бим', 'Белый Бим'), ('баланс бел', 'Баланс Белого'),
            ('кардымов', 'Кардымовское'), ('ейск', 'Ейское'),
            ('домашн', 'Домашнее'), ('дубов', 'Дубовый Бочонок'),
            ('вишнев', 'Вишневый Эль'), ('сидр', 'Сидр'),
            ('медовух', 'Медовуха')
        ]
        for k, canon in brands:
            if k in s: return f"{canon}{filt}"

        clean = re.sub(r'бирконг|пиво|светлое|темное|непастеризованн\w+|фильтрованн\w+|нефильтрованн\w+|\d+([.,]\d+)?%|хмельной|хмельная', '', s)
        clean = re.sub(r'\(.*?\)', '', clean)
        clean = re.sub(r'\s+', ' ', clean).strip().title()
        return f"{clean or str(name).strip()}{filt}"

    if not target_key:
        target_names = set(sales_df['Наименование'])
        is_beer_query = False
    else:
        mask_cat = cat_df['Группа товара'].str.lower().str.contains(target_key, na=False) | cat_df['Наименование'].str.lower().str.contains(target_key, na=False)
        names_from_cat = set(cat_df.loc[mask_cat, 'Наименование'])
        names_from_sales = set(sales_df.loc[sales_df['Наименование'].str.lower().str.contains(target_key, na=False), 'Наименование'])
        target_names = names_from_cat | names_from_sales
        is_beer_query = any(k in target_key for k in ['канцлер', 'пиво', 'маркирован', 'розлив', 'эль', 'сидр', 'медовух'])

    cat_sub = cat_df[['Наименование', 'Группа товара', 'Единица измерения']].drop_duplicates('Наименование')
    df = sales_df[sales_df['Наименование'].isin(target_names)].merge(cat_sub, on='Наименование', how='left')
    df['Единица измерения'] = df['Единица измерения'].fillna('шт').astype(str).str.lower()

    if is_beer_query:
        df['Каноническое_наименование'] = df['Наименование'].apply(normalize_beer_sku)
        df['Ед'] = 'л'
    else:
        df['Каноническое_наименование'] = df['Наименование']
        df['Ед'] = np.where(df['Единица измерения'].str.contains('кг'), 'кг', 'шт')

    df['Выручка'] = df['Цена продажи']
    df['Себестоимость'] = df['Цена закупки']
    df['Прибыль'] = df['Выручка'] - df['Себестоимость']

    p = df.groupby(['Каноническое_наименование', 'Ед'], as_index=False).agg(
        Продажи=('Количество', 'sum'),
        Выручка=('Выручка', 'sum'),
        Себестоимость=('Себестоимость', 'sum'),
        Прибыль=('Прибыль', 'sum'),
        Охват=('МАГАЗИН', lambda x: df.loc[x.index].loc[df.loc[x.index, 'Количество'] > 0, 'МАГАЗИН'].nunique())
    ).rename(columns={'Каноническое_наименование': 'Наименование'})

    p['Маржа'] = np.where(p['Выручка'] > 0, (p['Прибыль'] / p['Выручка']) * 100, 0)
    tot_rev = df['Выручка'].sum()
    tot_prof = df['Прибыль'].sum()
    avg_margin = (tot_prof / tot_rev * 100) if tot_rev > 0 else 0

    p = p.sort_values('Прибыль', ascending=False).reset_index(drop=True)
    p['Кум_Прибыль'] = p['Прибыль'].cumsum()
    drivers = p[(p['Кум_Прибыль'] - p['Прибыль'] < 0.8 * tot_prof) | (p['Кум_Прибыль'] <= 0.8 * tot_prof)]
    if drivers.empty and not p.empty: drivers = p.head(1)

    all_stores = sorted(sales_df['МАГАЗИН'].dropna().unique())
    num_stores = len(all_stores) if len(all_stores) > 0 else 14
    half_stores = max(1, num_stores // 2)

    gaps = p[(p['Охват'] < half_stores) & (p['Маржа'] >= max(40.0, avg_margin))].copy()
    gaps['Потенциал_прибыли'] = (gaps['Прибыль'] / gaps['Охват'].replace(0, 1)) * (num_stores - gaps['Охват'])
    deadstock = p[((p['Охват'] >= half_stores) & (p['Продажи'] < num_stores)) | (p['Маржа'] < 20)].copy()

    st = df.groupby('МАГАЗИН', as_index=False).agg(
        Выручка=('Выручка', 'sum'),
        Прибыль=('Прибыль', 'sum'),
        Объем=('Количество', 'sum')
    )
    st['Маржа'] = np.where(st['Выручка'] > 0, (st['Прибыль'] / st['Выручка']) * 100, 0)
    st['Доля'] = np.where(tot_rev > 0, (st['Выручка'] / tot_rev) * 100, 0)
    st = st.sort_values('Выручка', ascending=False).reset_index(drop=True)

    avg_store_rev = tot_rev / num_stores if num_stores > 0 else 0
    def get_cluster(row):
        if row['Выручка'] >= avg_store_rev * 1.2: return 'Флагман'
        if row['Выручка'] < avg_store_rev * 0.6: return 'Точка_риска'
        return 'Середняк'
    st['Кластер'] = st.apply(get_cluster, axis=1)
    zero_st = [s for s in all_stores if s not in df.loc[df['Количество'] > 0, 'МАГАЗИН'].unique()]

    tot_vol = df['Количество'].sum()
    unit_label = 'л' if is_beer_query else 'ед.'
    active_stores_count = df.loc[df['Количество'] > 0, 'МАГАЗИН'].nunique()

    print(f"СВОДКА|{tot_rev:.0f}|{tot_prof:.0f}|{avg_margin:.1f}|{tot_vol:.1f}|{unit_label}|{active_stores_count}|{gaps['Потенциал_прибыли'].sum():.0f}|{deadstock['Себестоимость'].sum():.0f}")

    print("ДРАЙВЕРЫ")
    for _, r in drivers.iterrows():
        print(f"D|{r['Наименование']}|{r['Ед']}|{r['Выручка']:.0f}|{r['Прибыль']:.0f}|{r['Маржа']:.1f}|{r['Охват']}|{(r['Прибыль']/tot_prof*100 if tot_prof else 0):.1f}")

    print("ДЫРЫ_ПОТЕНЦИАЛ")
    for _, r in gaps.sort_values('Потенциал_прибыли', ascending=False).head(5).iterrows():
        print(f"G|{r['Наименование']}|{r['Маржа']:.1f}|{r['Охват']}|{r['Потенциал_прибыли']:.0f}")

    print("БАЛЛАСТ")
    for _, r in deadstock.head(5).iterrows():
        print(f"B|{r['Наименование']}|{r['Продажи']:.1f}|{r['Маржа']:.1f}|{r['Охват']}|{r['Себестоимость']:.0f}")

    print("СЕТЬ_КЛАСТЕРЫ")
    for _, r in st.iterrows():
        print(f"S|{r['МАГАЗИН']}|{r['Кластер']}|{r['Выручка']:.0f}|{r['Прибыль']:.0f}|{r['Маржа']:.1f}|{r['Объем']:.1f}|{r['Доля']:.1f}")
    print("Z|" + (', '.join(zero_st) if zero_st else "нет"))

if __name__ == "__main__":
    main()