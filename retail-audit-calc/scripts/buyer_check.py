import os, sys, re, argparse, difflib, json, urllib.request
import os as _os, sys as _sys
_p = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _p not in _sys.path:
    _sys.path.insert(0, _p)
import pandas as pd
from scripts.normalizer import norm, clean_snack_name, get_tokens
from scripts.utils import is_g2_store, load_store_data, send_google_log, parse_items_arg

def determine_unit(row):
    u, n = str(row.get('cat_unit', '')).strip().lower(), str(row['clean_name']).lower()
    if any(k in n for k in ['чипсы из свинины', 'чипсы мясные свиные корейка', 'карпаччо', 'чипсы из курицы']) and not re.search(r'\b(75г|90г|50г|100г|в/у)\b', n): return 'кг'
    if 'чипсы мясные курица 75г' in n or 'чипсы мясные свинина 75г' in n: return 'шт'
    if any(k in n for k in ['шокоприз', 'яйцо', 'антистресс', 'леденец', 'чупа', 'мармелад на палочке', 'горшочек', 'gummy crazy', 'шнеллер']): return 'шт'
    if u in ['шт', 'шт.', 'упак']: return 'шт'
    if re.search(r'\b(75г|85г|90г|50г|95г|100г|130г|15г|24г|в/у|стакан|пакет|пачка)\b', n): return 'шт'
    if any(k in n for k in ['(вес)', ' вес', 'соломка', 'спинка', 'нарезка', 'фисташк', 'арахис', 'сыр нити', 'сыр коса', 'сухари', 'камбал', 'полосатик', 'кальмар', 'горбуша']): return 'кг'
    return 'кг' if 'кг' in u else ('шт' if u else 'кг')

def match_product(query_name, catalog_items):
    q_norm, q_tokens = norm(query_name), set(get_tokens(query_name))
    for item in catalog_items:
        if q_norm == item['norm']: return item
    # IMP-04: убрано опасное вхождение подстроки (q_norm in item['norm']),
    # дававшее ложные срабатывания на коротких запросах.
    # Ниже — токенизированный поиск и SequenceMatcher (не тронуты).

    best_item, best_score = None, 0.0
    for item in catalog_items:
        c_tokens = set(item['tokens'])
        if not c_tokens or not q_tokens: continue
        common = q_tokens.intersection(c_tokens)
        if not common: continue
        score = (len(common) / len(q_tokens)) * 0.75 + (len(common) / len(q_tokens.union(c_tokens))) * 0.25
        if score > best_score: best_score, best_item = score, item
    if best_score >= 0.32: return best_item

    best_ratio, fallback = 0.0, None
    for item in catalog_items:
        r = difflib.SequenceMatcher(None, q_norm, item['norm']).ratio()
        if r > best_ratio: best_ratio, fallback = r, item
    return fallback if best_ratio >= 0.45 else None

def main():
    parser = argparse.ArgumentParser(description="Buyer check tool")
    parser.add_argument("--store", required=True, help="Название магазина")
    parser.add_argument("--file", help="Путь к файлу со списком (опционально)")
    parser.add_argument("--items", default=None, help="Список позиций через точку с запятой")
    args = parser.parse_args()

    store_query = args.store.strip().lower()
    if store_query.startswith(('тест_', 'test_')): store_query = store_query.split('_', 1)[1]

    if args.items: items_raw = parse_items_arg(args.items)
    elif args.file and os.path.exists(args.file):
        with open(args.file, 'r', encoding='utf-8') as f: items_raw = [line.strip() for line in f if line.strip()]
    else: items_raw = [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]

    if not items_raw:
        print("Список товаров пуст."); return

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sales, cat, is_g2 = load_store_data(base_dir, store_query)
    if sales.empty:
        print("Ошибка: База продаж пуста или файл не найден."); return

    all_stores = sales['МАГАЗИН'].dropna().unique()
    target_store = None
    for st in all_stores:
        st_low = str(st).lower()
        if ('родник' in store_query or 'rodnik' in store_query) and ('родник' in st_low or 'rodnik' in st_low): target_store = st; break
        if ('батов' in store_query or 'batov' in store_query) and ('батов' in st_low or 'batov' in st_low): target_store = st; break
        if ('штем' in store_query or 'shtem' in store_query) and ('штем' in st_low or 'shtem' in st_low): target_store = st; break
        if store_query in st_low: target_store = st; break

    if not target_store:
        print(f"Ошибка: Магазин '{args.store}' не найден в выгрузке."); return

    send_google_log(args.store, 'Закупщик: проверка списка')

    cat_map_unit = dict(zip(cat['Наименование'].map(norm), cat.get('Единица измерения', pd.Series()).fillna('')))
    sales['norm_k'] = sales['Наименование'].map(norm)
    sales['cat_unit'] = sales['norm_k'].map(cat_map_unit).fillna('')
    sales['clean_name'] = sales['Наименование'].map(clean_snack_name)
    sales['final_unit'] = sales.apply(determine_unit, axis=1)

    st_df = sales[sales['МАГАЗИН'] == target_store].copy()
    agg_st = st_df.groupby(['clean_name', 'final_unit'])['Количество'].sum().reset_index()

    catalog_items = [{'clean_name': str(r['clean_name']), 'norm': norm(str(r['clean_name'])), 'tokens': get_tokens(str(r['clean_name'])), 'unit': r['final_unit'], 'qty_month': float(r['Количество'])} for _, r in agg_st.iterrows()]

    print(f"Магазин {str(target_store).upper()} — продажи за 7 дней:\n")
    for raw_query in items_raw:
        matched = match_product(raw_query, catalog_items)
        q_low = raw_query.lower()
        is_piece = re.search(r'\b(75г|85г|90г|50г|95г|100г|130г|15г|24г|в/у|стакан|пакет|пачка)\b', q_low) or any(k in q_low for k in ['шокоприз', 'яйцо', 'антистресс', 'леденец', 'мармелад', 'горшочек', 'чипсы мясные курица 75', 'чипсы мясные свинина 75', 'шнеллер'])
        default_u = 'шт' if is_piece else 'кг'

        if matched and matched['qty_month'] > 0:
            sales_7d = matched['qty_month'] * 0.25
            u = matched['unit']
            print(f"• {raw_query} — {sales_7d:.2f} кг" if u == 'кг' else f"• {raw_query} — {round(sales_7d)} шт")
        else:
            print(f"• {raw_query} — 0.00 кг" if default_u == 'кг' else f"• {raw_query} — 0 шт")

if __name__ == '__main__':
    main()