import os, sys, re, argparse, json, urllib.request
import os as _os, sys as _sys
_p = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _p not in _sys.path:
    _sys.path.insert(0, _p)
import pandas as pd
from scripts.normalizer import norm, clean_snack_name, canonicalize_beer
from scripts.utils import is_g2_store, find_store_in_list, load_store_data, send_google_log

SAFETY_FACTOR_DEFAULT = 1.15  # страховой запас (FIX-03), единый стандарт с buyer_audit.py, переопределяется через --safety-factor

def compact_ballast_name(name, g_title):
    s = str(name).strip()
    if g_title == 'Арахис':
        s = re.sub(r'^(арахис|ядра арахиса)\s+', '', s, flags=re.I)
    elif g_title == 'Сыры':
        s = re.sub(r'^сыр\s+', '', s, flags=re.I)
    s = re.sub(r'\s+со вкусом\s+', ' ', s, flags=re.I)
    return re.sub(r'\s+', ' ', s).strip(' ,"-')

def process_single_item(sales, cat, store_key, item_query, is_g2):
    all_stores = sales['МАГАЗИН'].dropna().unique()
    target_store = find_store_in_list(store_key, all_stores)
    if not target_store:
        print(f"Магазин '{store_key}' не найден"); return
    st_df = sales[sales['МАГАЗИН'] == target_store].copy()
    if st_df.empty:
        print(f"По магазину {target_store} нет данных о продажах"); return

    cat_map_unit = dict(zip(cat['Наименование'].map(norm), cat.get('Единица измерения', pd.Series()).fillna('')))
    st_df['norm_k'] = st_df['Наименование'].map(norm)
    st_df['cat_unit'] = st_df['norm_k'].map(cat_map_unit).fillna('').astype(str).str.lower().str.strip()

    q_norm = norm(item_query)
    if not q_norm.strip():
        print(f"{str(item_query).strip()} — 0 шт за 7 дней, 0 шт за 30 дней"); return
    matched = st_df[st_df['norm_k'].str.contains(re.escape(q_norm), na=False)]
    if matched.empty:
        tokens = [t for t in q_norm.split() if len(t) > 2]
        if tokens:
            mask = st_df['norm_k'].apply(lambda x: all(t in x for t in tokens))
            matched = st_df[mask]

    if matched.empty:
        print(f"{item_query.strip()} — 0 шт за 7 дней, 0 шт за 30 дней"); return

    agg = matched.groupby(['Наименование', 'cat_unit'])['Количество'].sum().reset_index()
    best = agg.sort_values('Количество', ascending=False).iloc[0]
    name, qty_30, unit = str(best['Наименование']).strip(), float(best['Количество']), best['cat_unit']
    qty_7 = qty_30 * 0.25

    if not unit or unit == 'nan':
        n_low = name.lower()
        if any(x in n_low for x in ['чипсы мясные 75', 'в/у', '0.5', '0.45', 'ж/б', 'ст', 'чупа', 'яйцо', 'шнеллер', 'пэт', 'стаканчик']): unit = 'шт'
        elif any(x in n_low for x in ['пиво', 'эль', 'квас', 'лимонад', 'сидр', 'медовуха']): unit = 'л'
        else: unit = 'кг'

    if unit in ['л', 'кг']: print(f"{name} — {qty_7:.2f} {unit} за 7 дней, {qty_30:.2f} {unit} за 30 дней")
    else: print(f"{name} — {int(round(qty_7))} {unit} за 7 дней, {int(round(qty_30))} {unit} за 30 дней")


def process_beer(sales, cat, store_key, is_g2, sf=SAFETY_FACTOR_DEFAULT):
    cat_map_grp = dict(zip(cat['Наименование'].map(norm), cat['Группа товара']))
    cat_map_unit = dict(zip(cat['Наименование'].map(norm), cat.get('Единица измерения', pd.Series()).fillna('')))
    sales['norm_k'] = sales['Наименование'].map(norm)
    sales['grp'] = sales['norm_k'].map(cat_map_grp).fillna('')
    sales['unit'] = sales['norm_k'].map(cat_map_unit).fillna('').astype(str).str.lower().str.strip()

    if is_g2:
        sales_b = sales[sales['grp'].str.lower().isin(['напитки', 'маркированный алкоголь']) & sales['unit'].isin(['л', 'кг'])].copy()
    else:
        is_packaged = (sales['unit'] == 'шт') | sales['grp'].str.contains('стекло|бутыл|банка|тара|детство|снеки|рыба|сыр', case=False, regex=True) | sales['Наименование'].str.contains(r'0\.45|0\.5|0\.75|0\.33|1\.5|ж/б| жб| ст |стекло|бутыл|владикавказ|бавария|слайсы|чипсы', case=False, regex=True)
        is_draft = (sales['grp'].str.contains('розлив|маркированный|напитки', case=False, regex=True) | sales['Наименование'].str.contains('пиво|эль|квас|лимонад|медовуха|сидр', case=False, regex=True)) & (~is_packaged)
        sales_b = sales[is_draft].copy()

    sales_b['canon'] = sales_b['Наименование'].map(canonicalize_beer)
    sales_b = sales_b[sales_b['canon'].astype(str).str.strip() != ''].copy()  # FIX-05: отсекаем исключённые позиции (канон = '')
    all_stores = sales_b['МАГАЗИН'].dropna().unique()
    target_store = find_store_in_list(store_key, all_stores)
    if not target_store: return

    st_df = sales_b[sales_b['МАГАЗИН'] == target_store]
    agg_st = st_df.groupby('canon')['Количество'].sum().reset_index()
    if agg_st.empty:
        print(f"BEER_SUMMARY|0|0.0|0.0|{len(all_stores)}"); return

    agg_st.columns = ['canon', 'qty_month']
    agg_st['rec_week'] = (agg_st['qty_month'] * sf / 4.0).round(1)
    agg_st = agg_st.sort_values('qty_month', ascending=False).reset_index(drop=True)
    print(f"BEER_SUMMARY|{len(agg_st)}|{round(agg_st['rec_week'].sum(), 1)}|{round(agg_st['qty_month'].sum(), 1)}|{len(all_stores)}")
    for idx, r in agg_st.iterrows(): print(f"CP|{idx+1}|{r['canon']}|{r['rec_week']}|{round(r['qty_month'], 1)}")

    st_all = sales[sales['МАГАЗИН'] == target_store].copy()
    is_tara = (st_all['grp'].str.contains('тара|пэт', case=False, regex=True) | st_all['Наименование'].str.contains(r'\bпэт\b|стаканчик|бутылка пэт', case=False, regex=True)) & (~st_all['Наименование'].str.contains('лимонад|пиво|квас', case=False, regex=True))
    tara_df = st_all[is_tara]
    if not tara_df.empty:
        for _, r in tara_df.groupby('Наименование')['Количество'].sum().sort_values(ascending=False).reset_index().iterrows():
            rec_tara = int(round(r['Количество'] * sf / 4.0))
            if rec_tara > 0 or r['Количество'] >= 10: print(f"TARA|{r['Наименование']}|{rec_tara}|{int(round(r['Количество']))}")

    ROT_BLACKLIST = ('ейское', 'кардымовское')
    net_agg = sales_b.groupby('canon')['Количество'].sum().sort_values(ascending=False).reset_index()
    current_canons = set(agg_st['canon'])
    rot_candidates = [r['canon'] for _, r in net_agg.iterrows() if r['canon'] not in current_canons and not any(bl in r['canon'].lower() for bl in ROT_BLACKLIST) and r['Количество'] >= 100.0][:5]
    for cn in rot_candidates: print(f"BROT|{cn}")
    for _, r in agg_st[agg_st['qty_month'] < 30.0].sort_values('qty_month').iterrows(): print(f"WP|{r['canon']}|{round(r['qty_month'], 1)}")

def clean_item_label(name, g_title):
    n = str(name).strip()
    if g_title == 'Арахис': n = re.sub(r'^(арахис|ядра арахиса)\s+', '', n, flags=re.I).strip()
    elif g_title == 'Сыры': n = re.sub(r'^сыр\s+', '', n, flags=re.I).strip()
    return n

def process_snacks(sales, cat, store_key, is_g2, sf=SAFETY_FACTOR_DEFAULT):
    cat_map_grp = dict(zip(cat['Наименование'].map(norm), cat['Группа товара']))
    cat_map_unit = dict(zip(cat['Наименование'].map(norm), cat.get('Единица измерения', pd.Series()).fillna('')))
    sales['norm_k'] = sales['Наименование'].map(norm)
    sales['grp'] = sales['norm_k'].map(cat_map_grp).fillna('')
    sales['cat_unit'] = sales['norm_k'].map(cat_map_unit).fillna('')
    sales['clean_name'] = sales['Наименование'].map(clean_snack_name)
    all_stores = sales['МАГАЗИН'].dropna().unique()
    target_store = find_store_in_list(store_key, all_stores)
    if not target_store: return

    def determine_unit(row):
        u, n = str(row.get('cat_unit', '')).strip().lower(), str(row['clean_name']).lower()
        if any(k in n for k in ['чипсы из свинины', 'чипсы мясные свиные корейка', 'карпаччо', 'чипсы из курицы']) and not re.search(r'\b(75г|90г|50г|100г|в/у)\b', n): return 'кг'
        if 'чипсы мясные курица 75г' in n or 'чипсы мясные свинина 75г' in n: return 'шт'
        if any(k in n for k in ['шокоприз', 'яйцо', 'антистресс', 'леденец', 'чупа', 'мармелад на палочке', 'горшочек', 'gummy crazy', 'шнеллер']): return 'шт'
        if u in ['шт', 'шт.', 'упак']: return 'шт'
        if re.search(r'\b(75г|85г|90г|50г|95г|100г|130г|15г|24г|в/у|стакан|пакет|пачка)\b', n): return 'шт'
        if any(k in n for k in ['(вес)', ' вес', 'соломка', 'спинка', 'нарезка', 'фисташк', 'арахис', 'сыр нити', 'сыр коса', 'сухари', 'камбал', 'полосатик', 'кальмар', 'горбуша']): return 'кг'
        return 'кг' if 'кг' in u else ('шт' if u else 'кг')

    sales['final_unit'] = sales.apply(determine_unit, axis=1)

    def get_snack_category(row):
        g, n = str(row['grp']).strip().lower(), str(row['clean_name']).lower()
        if 'рыба калач' in g or 'рыба сергей' in g: return None
        if 'арахис' in g or 'арахис' in n:
            if any(x in n for x in ['мартин', 'караван орехов', 'джинн', 'караван', '40г', '80г', '90г', '100г', '150г']): return None
            if 'арахис' in g or n.startswith('арахис') or 'ядра арахиса' in n: return 'Арахис'
        if any(x in n for x in ['чипсы мясные', 'чипсы из свинины', 'чипсы из курицы', 'карпаччо', 'уши к пиву', 'уши свиные', 'кнутики', 'колбаски мясные', 'мясные колбаски', 'строганина', 'шнеллер']) or 'мясо' in g: return 'Мясные снеки'
        if ('сыр' in g or n.startswith('сыр ')) and 'сухар' not in g and 'гренки' not in n and 'сухар' not in n: return 'Сыры'
        if any(x in g for x in ['сухар', 'гренки', 'чипсы']) or any(x in n for x in ['сухари', 'гренки', 'чипсы пшеничные', 'чипсы пшенично-ржаные']):
            if any(x in n for x in ['лейз', 'lay', 'принглс', 'от мартина']): return None
            return 'Гренки и сухарики'
        fish_keywords = ['икра', 'минтай', 'кальмар', 'вобла', 'лещ', 'корюшк', 'горбуш', 'щук', 'янтарн', 'анчоус', 'камбал', 'таран', 'судак', 'пелядь', 'семг', 'форел', 'сиг', 'чехон', 'паутинка', 'ставрид', 'осетр', 'тунец', 'сом ', 'сом,', 'сом вял', 'бычеглаз', 'лакедра', 'карась', 'осьминог', 'путассу', 'вомер', 'рыбец', 'синец', 'толстолоб', 'жерех']
        if (is_g2 and any(rg in g for rg in ['рыбн', 'новая закуска', 'закуска новый'])) or (not is_g2 and any(rg in g for rg in ['рыба', 'рыбн', 'новая закуска'])) or any(k in n for k in fish_keywords): return 'Рыбные снеки'
        return None

    sales['snack_cat'] = sales.apply(get_snack_category, axis=1)
    st_df = sales[sales['МАГАЗИН'] == target_store].copy()
    categories_order = ['Арахис', 'Сыры', 'Рыбные снеки', 'Мясные снеки', 'Гренки и сухарики']
    cat_codes = {'Арахис': 'А', 'Сыры': 'С', 'Рыбные снеки': 'Р', 'Мясные снеки': 'М', 'Гренки и сухарики': 'Г'}
    ballast_total, ballast_dict = 0, {c: [] for c in categories_order}

    net_stakan = sales[(sales['snack_cat'] == 'Гренки и сухарики') & (sales['clean_name'].str.contains('стакан', case=False, regex=True))]
    if not net_stakan.empty:
        net_stakan_agg = net_stakan.groupby('clean_name')['Количество'].sum().sort_values(ascending=False).reset_index()
        for _, r in net_stakan_agg.head(5).iterrows(): print(f"CT|{r['clean_name']}")
        cur_stakans = set(st_df[st_df['clean_name'].str.contains('стакан', case=False, regex=True)]['clean_name'])
        for item in [r['clean_name'] for _, r in net_stakan_agg.iterrows() if r['clean_name'] not in cur_stakans][:3]: print(f"CR|{item}")

    for g_title in categories_order:
        code = cat_codes[g_title]
        sub = st_df[st_df['snack_cat'] == g_title]
        if sub.empty: continue
        agg = sub.groupby(['clean_name', 'final_unit'])['Количество'].sum().reset_index()
        if agg.empty: continue

        THRESH_KG, THRESH_PC = 1.0, {'Сыры': 15.0}.get(g_title, 10.0)
        def is_priority_meat(nm): return any(k in str(nm).lower() for k in ['чипсы мясные', 'чипсы из свинины', 'карпаччо'])
        def in_main(row):
            q, u, nm = row['Количество'], row['final_unit'], str(row['clean_name']).lower()
            if g_title == 'Гренки и сухарики' and 'стакан' in nm: return False
            if u == 'кг': return q >= THRESH_KG
            if g_title == 'Мясные снеки' and is_priority_meat(nm): return True
            return q >= THRESH_PC

        agg['in_main'] = agg.apply(in_main, axis=1)
        MIN_MAIN, n_main = 10, int(agg['in_main'].sum())
        if n_main < MIN_MAIN:
            cand = agg[~agg['in_main']].copy()
            if g_title == 'Гренки и сухарики': cand = cand[~cand['clean_name'].str.contains('стакан', case=False, regex=True)]
            if not cand.empty: agg.loc[cand.sort_values('Количество', ascending=False).head(MIN_MAIN - n_main).index, 'in_main'] = True

        main_df = agg[agg['in_main']].copy()
        if g_title == 'Сыры': main_df['prio'] = main_df['final_unit'].apply(lambda x: 0 if x == 'кг' else 1); main_df = main_df.sort_values(['prio', 'Количество'], ascending=[True, False])
        elif g_title == 'Мясные снеки': main_df['prio'] = main_df['clean_name'].apply(lambda x: 0 if is_priority_meat(x) else 1); main_df = main_df.sort_values(['prio', 'Количество'], ascending=[True, False])
        else: main_df = main_df.sort_values('Количество', ascending=False)

        for _, r in main_df.iterrows():
            rec = int(round(r['Количество'] * sf / 4.0)) if r['final_unit'] == 'шт' else round(r['Количество'] * sf / 4.0, 2)
            item_name = re.sub(r'\s+(сушено-вялен[а-я]+|солено-сушен[а-я]+)\b', '', re.sub(r'\s+со вкусом\s+', ' ', str(r['clean_name']), flags=re.I), flags=re.I).strip()
            print(f"SP|{code}|{item_name}|{r['final_unit']}|{rec}|{round(r['Количество'], 2)}")

        ballast_items = agg[~agg['in_main']].sort_values('Количество')
        if g_title == 'Гренки и сухарики': ballast_items = ballast_items[~ballast_items['clean_name'].str.contains('стакан', case=False, regex=True)]
        ballast_total += len(ballast_items)
        for _, r in ballast_items.iterrows():
            lbl = compact_ballast_name(r['clean_name'], g_title)
            ballast_dict[g_title].append(f"{lbl}:{round(r['Количество'], 2)}{r['final_unit']}")

        net_sub = sales[sales['snack_cat'] == g_title]
        if not net_sub.empty:
            net_agg = net_sub.groupby(['clean_name', 'final_unit'])['Количество'].sum().reset_index()
            cur_names = set(sub['clean_name'])
            rot_list = []
            for _, r in net_agg.sort_values('Количество', ascending=False).iterrows():
                if r['clean_name'] not in cur_names:
                    min_sales = 30.0 if r['final_unit'] == 'шт' else (5.0 if is_g2 else 10.0)
                    if r['Количество'] >= min_sales:
                        lbl = clean_item_label(r['clean_name'], g_title)
                        if lbl not in rot_list: rot_list.append(lbl)
                if len(rot_list) >= 2: break
            for lbl in rot_list: print(f"ROT|{code}|{lbl}")

    print(f"BALLAST_SUMMARY|{ballast_total}")
    for g_title in categories_order:
        items_str = "; ".join(ballast_dict[g_title])
        if items_str: print(f"B_GRP|{cat_codes[g_title]}|{items_str}")

def process_glass(sales, cat, store_key, is_g2, sf=SAFETY_FACTOR_DEFAULT):
    cat_map_grp = dict(zip(cat['Наименование'].map(norm), cat['Группа товара']))
    cat_map_unit = dict(zip(cat['Наименование'].map(norm), cat.get('Единица измерения', pd.Series()).fillna('')))
    sales['norm_k'] = sales['Наименование'].map(norm)
    sales['grp'] = sales['norm_k'].map(cat_map_grp).fillna('').astype(str)
    sales['unit'] = sales['norm_k'].map(cat_map_unit).fillna('').astype(str).str.lower().str.strip()

    is_tara = sales['grp'].str.contains('тара|пэт', case=False, regex=True) | sales['Наименование'].str.contains(r'\bпэт\b|стаканчик|бутылка пэт|пробка', case=False, regex=True)
    is_glass = ((sales['grp'].str.lower().str.contains('стекло|бавария|морава|воронеж', regex=True) | sales['Наименование'].str.contains(r'0\.45|0\.5|0\.75|0\.33|1\.5|ж/б| жб| ст |стекло|бутыл', case=False, regex=True)) & (sales['unit'] == 'шт')) & (~is_tara)
    glass_sales = sales[is_glass].copy()
    all_stores = glass_sales['МАГАЗИН'].dropna().unique()
    target_store = find_store_in_list(store_key, all_stores)
    if not target_store: return

    st_df = glass_sales[glass_sales['МАГАЗИН'] == target_store]
    agg = st_df.groupby('Наименование')['Количество'].sum().reset_index()
    if agg.empty: return

    for idx, r in agg[agg['Количество'] >= 10.0].sort_values('Количество', ascending=False).reset_index(drop=True).iterrows():
        print(f"GP|{idx+1}|{r['Наименование']}|{int(round(r['Количество'] * sf / 4.0))}|{int(round(r['Количество']))}")

    net_agg = glass_sales.groupby('Наименование')['Количество'].sum().reset_index()
    cur_names = set(st_df['Наименование'])
    for item in net_agg[(~net_agg['Наименование'].isin(cur_names)) & (net_agg['Количество'] >= 25.0)].sort_values('Количество', ascending=False).head(12)['Наименование']:
        print(f"GROT|{item}")
    for _, r in agg[agg['Количество'] < 10.0].sort_values('Количество').reset_index(drop=True).iterrows():
        print(f"GB|{r['Наименование']}|{int(round(r['Количество']))}")

def process_kids(sales, cat, store_key, is_g2, sf=SAFETY_FACTOR_DEFAULT):
    cat_map_grp = dict(zip(cat['Наименование'].map(norm), cat['Группа товара']))
    sales['grp'] = sales['Наименование'].map(norm).map(cat_map_grp).fillna('')
    kids_sub = sales[sales['grp'].str.lower().str.contains('детск|детств', regex=True)].copy() if is_g2 else sales[sales['grp'].str.contains('дет|слад|конфет|сок', case=False, regex=True) | sales['Наименование'].str.contains('чупа|конфет|карамел|жеват|дет', case=False, regex=True)].copy()
    all_stores = kids_sub['МАГАЗИН'].dropna().unique()
    target_store = find_store_in_list(store_key, all_stores)
    if not target_store: return

    st_df = kids_sub[kids_sub['МАГАЗИН'] == target_store]
    agg = st_df.groupby('Наименование')['Количество'].sum().reset_index()
    STRATEGIC_KIDS = ['лучистик', 'crazy sushi', 'шокоприз', 'мороженка', 'горшочек прикольный']
    is_strategic = lambda name: any(s in str(name).lower() for s in STRATEGIC_KIDS)

    if not agg.empty:
        agg = agg.sort_values('Количество', ascending=False)
        for idx, r in agg[(agg['Количество'] >= 10.0) | agg['Наименование'].apply(is_strategic)].reset_index(drop=True).iterrows():
            print(f"KP|{idx+1}|{r['Наименование']}|шт|{int(round(r['Количество'] * sf / 4.0))}|{int(round(r['Количество']))}")
        for _, r in agg[(agg['Количество'] < 10.0) & (~agg['Наименование'].apply(is_strategic))].sort_values('Количество').iterrows():
            print(f"KB|{r['Наименование']}|{int(round(r['Количество']))}")

    net_agg = kids_sub.groupby('Наименование')['Количество'].sum().reset_index()
    cur_names = set(st_df['Наименование'])
    for item in net_agg[(~net_agg['Наименование'].isin(cur_names)) & (net_agg['Количество'] >= 30.0)].sort_values('Количество', ascending=False).head(5)['Наименование']:
        print(f"KROT|{item}")

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--cat', type=str, default='beer')
    parser.add_argument('--store', type=str, default='')
    parser.add_argument('--item', type=str, default=None, help='Поиск одной позиции')
    parser.add_argument('--safety-factor', dest='safety_factor', type=float, default=SAFETY_FACTOR_DEFAULT,
                        help='Коэффициент страхового запаса для недельного заказа (FIX-03)')
    args, _ = parser.parse_known_args(argv)
    sf = args.safety_factor if args.safety_factor and args.safety_factor > 0 else SAFETY_FACTOR_DEFAULT

    log_category = "справка по позиции" if args.item else args.cat
    send_google_log(args.store, log_category)

    clean_store = args.store
    if not str(clean_store).strip():
        print("ERR|Не указан магазин (--store)"); return
    if str(args.store).lower().startswith(('тест_', 'test_')):
        clean_store = args.store.split('_', 1)[1]

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sales, cat, is_g2 = load_store_data(base_dir, clean_store)
    if sales.empty: return

    if args.item:
        process_single_item(sales, cat, clean_store, args.item, is_g2)
        return

    if args.cat == 'beer': process_beer(sales, cat, clean_store, is_g2, sf)
    elif args.cat == 'snacks': process_snacks(sales, cat, clean_store, is_g2, sf)
    elif args.cat == 'glass': process_glass(sales, cat, clean_store, is_g2, sf)
    elif args.cat == 'kids': process_kids(sales, cat, clean_store, is_g2, sf)

if __name__ == '__main__':
    main()
