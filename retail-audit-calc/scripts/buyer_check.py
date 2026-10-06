import os, sys, re, argparse, difflib, json, urllib.request
import os as _os, sys as _sys

_p = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _p not in _sys.path:
    _sys.path.insert(0, _p)

import pandas as pd
from scripts.normalizer import norm, clean_snack_name, get_tokens
from scripts.utils import is_g2_store, load_store_data, send_google_log, parse_items_arg, match_sales_by_query, resolve_store

def determine_unit(row):
    u, n = str(row.get('cat_unit', '')).strip().lower(), str(row['clean_name']).lower()
    if any(k in n for k in ['чипсы из свинины', 'чипсы мясные свиные корейка', 'карпаччо', 'чипсы из курицы']) and not re.search(r'\b(75г|90г|50г|100г|в/у)\b', n): return 'кг'
    if 'чипсы мясные курица 75г' in n or 'чипсы мясные свинина 75г' in n: return 'шт'
    if any(k in n for k in ['шокоприз', 'яйцо', 'антистресс', 'леденец', 'чупа', 'мармелад на палочке', 'горшочек', 'gummy crazy', 'шнеллер']): return 'шт'
    if u in ['шт', 'шт.', 'упак']: return 'шт'
    if re.search(r'\b(75г|85г|90г|50г|95г|100г|130г|15г|24г|в/у|стакан|пакет|пачка)\b', n): return 'шт'
    if any(k in n for k in ['(вес)', ' вес', 'соломка', 'спинка', 'нарезка', 'фисташк', 'арахис', 'сыр нити', 'сыр коса', 'сухари', 'камбал', 'полосатик', 'кальмар', 'горбуша']): return 'кг'
    return 'кг' if 'кг' in u else ('шт' if u else 'кг')

# B23/IMP-07: локальный match_product удалён — используется единый
# match_sales_by_query из scripts/utils.py (три ступени: подстрока ->
# токены в любом порядке -> токен-нечёткость difflib >= 0.8).

def main():
    parser = argparse.ArgumentParser(description="Buyer check tool")
    parser.add_argument("--store", required=True, help="Название магазина")
    parser.add_argument("--file", help="Путь к файлу со списком (опционально)")
    parser.add_argument("--items", default=None, help="Список позиций через точку с запятой")
    parser.add_argument("--days", type=int, default=7, help="Горизонт расчёта в днях (B23: явное окно)")
    args = parser.parse_args()

    store_query = args.store.strip().lower()
    if store_query.startswith(('тест_', 'test_')): 
        store_query = store_query.split('_', 1)[1]

    if args.items: 
        items_raw = parse_items_arg(args.items)
    elif args.file and os.path.exists(args.file):
        with open(args.file, 'r', encoding='utf-8') as f: 
            items_raw = [line.strip() for line in f if line.strip()]
    else: 
        items_raw = [line.strip() for line in sys.stdin.read().splitlines() if line.strip()]

    if not items_raw:
        print("Список товаров пуст.")
        return

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sales, cat, is_g2 = load_store_data(base_dir, store_query)
    if sales.empty:
        print("Ошибка: База продаж пуста или файл не найден.")
        return

    all_stores = list(sales['МАГАЗИН'].dropna().unique())
    target_store = resolve_store(store_query, all_stores)

    if not target_store:
        print(f"Ошибка: Магазин '{args.store}' не найден в выгрузке.")
        return

    send_google_log(args.store, 'Закупщик: проверка списка')

    cat_map_unit = dict(zip(cat['Наименование'].map(norm), cat.get('Единица измерения', pd.Series()).fillna('')))
    sales['norm_k'] = sales['Наименование'].map(norm)
    sales['cat_unit'] = sales['norm_k'].map(cat_map_unit).fillna('')
    sales['clean_name'] = sales['Наименование'].map(clean_snack_name)
    sales['final_unit'] = sales.apply(determine_unit, axis=1)

    st_df = sales[sales['МАГАЗИН'] == target_store].copy()
    frac = args.days / 30.0

    print(f"ПЕРИОД|{args.days}")
    print(f"Магазин {str(target_store).upper()} — продажи за {args.days} дней:\n")
    
    for raw_query in items_raw:
        mask = match_sales_by_query(st_df, raw_query)
        matched_rows = st_df[mask]
        q_low = raw_query.lower()
        is_piece = re.search(r'\b(75г|85г|90г|50г|95г|100г|130г|15г|24г|в/у|стакан|пакет|пачка)\b', q_low) or any(k in q_low for k in ['шокоприз', 'яйцо', 'антистресс', 'леденец', 'мармелад', 'горшочек', 'чипсы мясные курица 75', 'чипсы мясные свинина 75', 'шнеллер'])
        default_u = 'шт' if is_piece else 'кг'

        total_qty = 0.0
        unit_used = None
        if not matched_rows.empty:
            per_sku = matched_rows.groupby(['clean_name', 'final_unit'])['Количество'].sum().reset_index()
            per_sku = per_sku.sort_values('Количество', ascending=False)
            for _, r in per_sku.iterrows():
                qn = float(r['Количество']) * frac
                total_qty += qn
                if unit_used is None: unit_used = r['final_unit']
                print(f"MATCH|{r['clean_name']}|{qn:.2f}")
            
            u = unit_used or default_u
            if u == 'кг':
                print(f"• {raw_query} — ИТОГО {total_qty:.2f} кг")
            elif u == 'л':
                print(f"• {raw_query} — ИТОГО {total_qty:.2f} л")
            else:
                print(f"• {raw_query} — ИТОГО {int(round(total_qty))} {u}")
        else:
            print(f"• {raw_query} — 0.00 кг" if default_u == 'кг' else f"• {raw_query} — 0 шт")

if __name__ == '__main__':
    main()