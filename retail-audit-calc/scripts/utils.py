"""Общие утилиты для скриптов retail-audit-calc (IMP-01)."""
import difflib
import os
import re
import json
import threading
import urllib.request
import pandas as pd
from scripts.normalizer import norm, get_tokens

WEBHOOK_TOKEN = 'YOUR_SECRET_TOKEN_HERE'
WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbwyFOdcITCcIecR-kN7RLO4GnwDn6tqGYa2a64kcMa4YLunOESDZ6NV2hIZWaEv0cq2pw/exec"

def send_google_log(store, cat):
    """IMP-05: неблокирующая отправка лога в daemon-потоке."""
    def _send():
        if str(store).lower().startswith(('тест_', 'test_')):
            return
        try:
            payload = json.dumps({"store": store, "category": cat}).encode('utf-8')
            url_with_token = f"{WEBHOOK_URL}?token={WEBHOOK_TOKEN}" if WEBHOOK_TOKEN != 'YOUR_SECRET_TOKEN_HERE' else WEBHOOK_URL
            req = urllib.request.Request(url_with_token, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
            urllib.request.urlopen(req, timeout=3)
        except Exception:
            pass
    thread = threading.Thread(target=_send, daemon=True)
    thread.start()

def is_g2_store(store_key):
    k = str(store_key).lower().strip()
    return any(x in k for x in ['батов', 'штем', 'родник', 'batov', 'shtem', 'rodnik', 'shtmen'])

def find_store_in_list(store_key, store_list):
    sk = str(store_key).lower().strip()
    for st in store_list:
        stl = str(st).lower()
        if ('родник' in sk or 'rodnik' in sk) and ('родник' in stl or 'rodnik' in stl): return st
        if ('батов' in sk or 'batov' in sk) and ('батов' in stl or 'batov' in stl): return st
        if ('штем' in sk or 'shtem' in sk or 'shtmen' in sk) and ('штем' in stl or 'shtem' in stl or 'shtmen' in stl): return st
        if sk in stl: return st
    return None

def load_store_data(base_dir, store_key):
    is_g2 = is_g2_store(store_key)
    sf = 'sales_g2.xlsx' if is_g2 else 'sales.xlsx'
    cf = 'catalog_g2.xlsx' if is_g2 else 'catalog.xlsx'
    sp, cp = os.path.join(base_dir, sf), os.path.join(base_dir, cf)
    sales, cat = pd.DataFrame(), pd.DataFrame()
    if os.path.exists(sp):
        sales = pd.read_excel(sp, header=1)
        sales.columns = [str(c).strip() for c in sales.columns]
        sales['Количество'] = pd.to_numeric(sales['Количество'], errors='coerce').fillna(0)
        sales = sales[sales['Количество'] > 0].copy()
    if os.path.exists(cp):
        cat = pd.read_excel(cp, header=0)
        cat.columns = [str(c).strip() for c in cat.columns]
        cat = cat.drop_duplicates(subset=['Наименование'])
    return sales, cat, is_g2

def parse_items_arg(items_str):
    return [item.strip() for item in items_str.split(';') if item.strip()] if items_str else []

# ---------------------------------------------------------------------------
# IMP-07 / B23: единый слой матчинга позиций и разрешения магазинов.
# ---------------------------------------------------------------------------
STORE_ALIASES = {
    'нариманов': 'нариманова',
    'нариманова': 'нариманов',
    'порт': 'порт-саида',
    'порт-саида': 'порт',
}

def match_sales_by_query(df, query):
    """Единый трёхступенчатый поиск позиций. Возвращает булеву маску по df."""
    names = df['Наименование'].astype(str)
    if query is None or not str(query).strip():
        return pd.Series([False] * len(df), index=df.index)
    q_norm = norm(query)
    mask_sub = names.map(lambda x: (q_norm in norm(x)) or (norm(x) in q_norm and len(norm(x)) >= 4))
    q_tokens = [t for t in get_tokens(query) if len(t) > 2]
    mask_tok = pd.Series([False] * len(df), index=df.index)
    mask_fuzzy = pd.Series([False] * len(df), index=df.index)
    if q_tokens:
        def _tok_all(x):
            n = norm(x)
            return all(t in n for t in q_tokens)
        mask_tok = names.map(_tok_all)
        def _tok_fuzzy(x):
            name_tokens = [t for t in get_tokens(x) if len(t) > 2]
            if not name_tokens:
                return False
            for qt in q_tokens:
                best = max(difflib.SequenceMatcher(None, qt, nt).ratio() for nt in name_tokens)
                if best < 0.8:
                    return False
            return True
        need_fuzzy = ~(mask_sub | mask_tok)
        if need_fuzzy.any():
            mask_fuzzy = names.where(need_fuzzy).map(lambda x: _tok_fuzzy(x) if isinstance(x, str) else False)
            mask_fuzzy = mask_fuzzy.fillna(False).astype(bool)
    return mask_sub | mask_tok | mask_fuzzy

def resolve_store(key, stores):
    """Единое разрешение магазина: точное -> key в store -> store в key -> алиасы -> difflib >= 0.85."""
    stores = list(stores)
    sk = str(key).lower().strip()
    if sk.startswith(('тест_', 'test_')):
        sk = sk.split('_', 1)[1]
    
    def _match_one(k):
        for st in stores:
            if str(st).lower().strip() == k:
                return st
        for st in stores:
            if k and k in str(st).lower():
                return st
        for st in sorted(stores, key=lambda s: -len(str(s))):
            stl = str(st).lower().strip()
            if stl and stl in k:
                return st
        alias = STORE_ALIASES.get(k)
        if alias:
            for st in stores:
                stl = str(st).lower().strip()
                if stl == alias or alias in stl or (stl and stl in alias):
                    return st
        best, best_ratio = None, 0.0
        for st in stores:
            r = difflib.SequenceMatcher(None, k, str(st).lower().strip()).ratio()
            if r > best_ratio:
                best_ratio, best = r, st
        return best if best_ratio >= 0.85 else None
    
    return _match_one(sk)