import os, sys, argparse, math, re
import pandas as pd
import numpy as np

ALLOWED_GROUPS = [
    'арахис', 'детств', 'мясо', 'новая закуска', 
    'рыба снеки', 'рыбные снеки', 'семечки', 'кукуруза', 'сухар', 'гренки', 'сыр', 'чипсы'
]

STRATEGIC_KIDS = [
    'лучистик', 'crazy sushi', 'шокоприз', 'мороженка', 'горшочек прикольный'
]

def norm_str(s):
    return re.sub(r'\s+', ' ', str(s).strip().lower().replace('"', '').replace("'", ''))

def canonicalize_sku(name):
    """Сквозная нормализация названий для объединения одинаковых товаров из G1 и G2"""
    raw = str(name).strip()
    s = norm_str(raw)
    
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

def determine_unit(name, cat_unit):
    """Строгое разделение штучных упаковок и развесного товара"""
    n = norm_str(name)
    u = str(cat_unit).lower().strip()
    
    # Жесткие штучные маркеры
    if any(x in n for x in ['75г', '90г', '50г', '95г', '100г', '130г', 'стакан', 'пакет', 'пачка', 'в/у', 'в\\у']):
        if 'карпаччо' not in n or '75г' in n:
            return 'шт'
    if u in ['шт', 'шт.', 'упак']:
        return 'шт'
    return 'кг'

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--group", type=str, default="", help="Фильтр по группе или SKU")
    parser.add_argument("--days", type=int, default=14, help="Горизонт заказа в днях")
    args = parser.parse_args()
    
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    query = args.group.strip().lower()

    def get_path(fname):
        p1 = os.path.join(base_dir, fname)
        if os.path.exists(p1): return p1
        p2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), fname)
        if os.path.exists(p2): return p2
        return fname

    # Чтение продаж (G1 + G2)
    s1, s2 = get_path('sales.xlsx'), get_path('sales_g2.xlsx')
    sales_dfs = []
    if os.path.exists(s1): sales_dfs.append(pd.read_excel(s1, header=1))
    if os.path.exists(s2): sales_dfs.append(pd.read_excel(s2, header=1))
    
    if not sales_dfs:
        print("ERR|Файлы продаж не найдены")
        return
        
    df_sales = pd.concat(sales_dfs, ignore_index=True)
    df_sales['Наименование'] = df_sales['Наименование'].astype(str).str.strip()
    df_sales['МАГАЗИН'] = df_sales['МАГАЗИН'].astype(str).str.strip()
    df_sales['Количество'] = pd.to_numeric(df_sales['Количество'], errors='coerce').fillna(0)
    df_sales = df_sales[df_sales['Количество'] > 0].copy()

    # Чтение справочников (G1 + G2)
    c1, c2 = get_path('catalog.xlsx'), get_path('catalog_g2.xlsx')
    cat_dfs = []
    if os.path.exists(c1): cat_dfs.append(pd.read_excel(c1))
    if os.path.exists(c2): cat_dfs.append(pd.read_excel(c2))
    
    cat_map_grp = {}
    cat_map_unit = {}
    if cat_dfs:
        df_cat = pd.concat(cat_dfs, ignore_index=True)
        df_cat['Наименование'] = df_cat['Наименование'].astype(str).str.strip()
        df_cat['Группа товара'] = df_cat['Группа товара'].astype(str).str.strip()
        df_cat['Единица измерения'] = df_cat.get('Единица измерения', pd.Series()).fillna('').astype(str).str.strip().str.lower()
        
        for _, r in df_cat.drop_duplicates('Наименование').iterrows():
            k = norm_str(r['Наименование'])
            cat_map_grp[k] = r['Группа товара']
            cat_map_unit[k] = r['Единица измерения']

    df_sales['norm_k'] = df_sales['Наименование'].map(norm_str)
    df_sales['Группа товара'] = df_sales['norm_k'].map(cat_map_grp).fillna('')
    df_sales['raw_unit'] = df_sales['norm_k'].map(cat_map_unit).fillna('')

    # Приведение к каноническому SKU и правильной единице измерения
    df_sales['Canon_SKU'] = df_sales['Наименование'].map(canonicalize_sku)
    df_sales['Ед'] = df_sales.apply(lambda r: determine_unit(r['Canon_SKU'], r['raw_unit']), axis=1)

    # Определение расширенной категории товара
    def get_broad_category(row):
        g = norm_str(row['Группа товара'])
        n = norm_str(row['Canon_SKU'])
        if any(x in n for x in ['чипсы мясные', 'карпаччо', 'уши к пиву', 'уши свиные', 'кнутики', 'колбаски мясные', 'мясные колбаски', 'строганина']) or 'мясо' in g:
            return 'мясо'
        if 'арахис' in g or 'арахис' in n or 'фисташк' in n:
            return 'арахис'
        if 'сыр' in g or n.startswith('сыр'):
            return 'сыр'
        if 'рыб' in g or 'рыба' in g:
            return 'рыба снеки'
        if any(x in g for x in ['сухар', 'гренки']) or any(x in n for x in ['сухари', 'гренки']):
            return 'сухари/гренки'
        if 'дет' in g or any(x in n for x in ['чупа', 'конфет', 'мармелад', 'карамель']):
            return 'детство'
        return g

    df_sales['Broad_Grp'] = df_sales.apply(get_broad_category, axis=1)

    # Фильтрация по Scope закупок
    def is_allowed(row):
        t = (str(row['Broad_Grp']) + " " + str(row['Группа товара']) + " " + str(row['Canon_SKU'])).lower()
        return any(ag in t for ag in ALLOWED_GROUPS)

    df = df_sales[df_sales.apply(is_allowed, axis=1)].copy()

    # Фильтр пользователя по группе
    if query:
        df = df[
            df['Broad_Grp'].str.contains(query, na=False) |
            df['Группа товара'].str.lower().str.contains(query, na=False) |
            df['Canon_SKU'].str.lower().str.contains(query, na=False)
        ].copy()

    if df.empty:
        print("ERR|Нет данных по запрошенной группе")
        return

    all_stores = sorted(df_sales['МАГАЗИН'].unique())
    total_stores_cnt = len(all_stores) if all_stores else 14

    # Агрегация по каноническому SKU (склеивает G1 и G2)
    sku_agg = df.groupby(['Canon_SKU', 'Ед'], as_index=False).agg(
        Продажи=('Количество', 'sum'),
        Охват=('МАГАЗИН', 'nunique')
    )

    # 1. СВОДКА
    df_pcs = sku_agg[sku_agg['Ед'] == 'шт']
    df_kg = sku_agg[sku_agg['Ед'] == 'кг']
    
    tot_pcs = df_pcs['Продажи'].sum()
    rate_pcs = tot_pcs / 30.0
    tot_kg = df_kg['Продажи'].sum()
    rate_kg = tot_kg / 30.0
    active_stores = df['МАГАЗИН'].nunique()
    
    print(f"СВОДКА|{int(round(tot_pcs))}|{rate_pcs:.1f}|{tot_kg:.1f}|{rate_kg:.2f}|{active_stores}")

    # 2. ЛИДЕРЫ (Группа А — 80% объема внутри каждой единицы измерения)
    print("ЛИДЕРЫ_А")
    for sub_df, unit, tot_vol in [(df_pcs, 'шт', tot_pcs), (df_kg, 'кг', tot_kg)]:
        if tot_vol <= 0: continue
        sorted_sub = sub_df.sort_values('Продажи', ascending=False).reset_index(drop=True)
        sorted_sub['cumsum'] = sorted_sub['Продажи'].cumsum()
        top_a = sorted_sub[(sorted_sub['cumsum'] - sorted_sub['Продажи'] < 0.8 * tot_vol) | (sorted_sub['cumsum'] <= 0.8 * tot_vol)]
        
        # Гарантируем вывод хотя бы ТОП-3, если кумулятивная сумма набралась слишком быстро
        if len(top_a) < 3 and len(sorted_sub) >= 3:
            top_a = sorted_sub.head(3)

        for _, r in top_a.iterrows():
            daily_rate = r['Продажи'] / 30.0
            order_14 = (daily_rate * args.days) * 1.15
            ord_str = f"{int(math.ceil(order_14))}" if unit == 'шт' else f"{order_14:.2f}"
            rate_str = f"{daily_rate:.1f}" if unit == 'шт' else f"{daily_rate:.2f}"
            vol_str = f"{int(round(r['Продажи']))}" if unit == 'шт' else f"{r['Продажи']:.2f}"
            print(f"L|{r['Canon_SKU']}|{unit}|{vol_str}|{rate_str}|{r['Охват']}|{ord_str}")

    # 3. ПРОБЛЕМНЫЕ ПОЗИЦИИ (Дыры дистрибуции или Балласт)
    print("ПРОБЛЕМНЫЕ")
    for _, r in sku_agg.iterrows():
        nm_low = r['Canon_SKU'].lower()
        is_strategic = any(sk in nm_low for sk in STRATEGIC_KIDS)
        
        # Стратегические детские позиции не считаем неликвидом
        if is_strategic:
            continue
            
        # Дыра в дистрибуции (хорошие продажи на точку, но охват меньше половины сети)
        sales_per_store = r['Продажи'] / r['Охват'] if r['Охват'] > 0 else 0
        if r['Охват'] < (total_stores_cnt // 2) and (r['Продажи'] >= 5 or sales_per_store >= 2.0):
            vol_str = f"{int(round(r['Продажи']))}" if r['Ед'] == 'шт' else f"{r['Продажи']:.2f}"
            print(f"P|{r['Canon_SKU']}|{r['Ед']}|{vol_str}|{r['Охват']}|Дыра_в_дистрибуции")
            
        # Неликвид (слабые суммарные продажи при широкой представленности)
        elif (r['Продажи'] < 14 and r['Охват'] >= (total_stores_cnt // 2)) or \
             ('сыр' in nm_low and 'пряд' in nm_low and r['Продажи'] < 40) or \
             ('детств' in nm_low and r['Продажи'] < 80):
            vol_str = f"{int(round(r['Продажи']))}" if r['Ед'] == 'шт' else f"{r['Продажи']:.2f}"
            print(f"P|{r['Canon_SKU']}|{r['Ед']}|{vol_str}|{r['Охват']}|Неликвид")

    # 4. СРЕЗ ПО МАГАЗИНАМ
    print("МАГАЗИНЫ")
    st_agg = df.groupby('МАГАЗИН').agg(
        Шт=('Количество', lambda x: df.loc[x.index].loc[df.loc[x.index, 'Ед'] == 'шт', 'Количество'].sum()),
        Кг=('Количество', lambda x: df.loc[x.index].loc[df.loc[x.index, 'Ед'] == 'кг', 'Количество'].sum()),
        Всего=('Количество', 'sum')
    ).reset_index().sort_values('Всего', ascending=False)
    
    net_total_vol = df['Количество'].sum()
    for _, r in st_agg.iterrows():
        share = (r['Всего'] / net_total_vol * 100) if net_total_vol > 0 else 0
        print(f"M|{r['МАГАЗИН']}|{int(round(r['Шт']))}|{r['Кг']:.1f}|{share:.1f}")

    zero_stores = [s for s in all_stores if s not in df['МАГАЗИН'].unique()]
    print("Z|" + (', '.join(zero_stores) if zero_stores else "нет"))

if __name__ == '__main__':
    main()