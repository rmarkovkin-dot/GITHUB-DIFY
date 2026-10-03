"""Общие утилиты для скриптов retail-audit-calc (IMP-01)."""
import os
import re
import json
import threading
import urllib.request
import pandas as pd

WEBHOOK_TOKEN = 'YOUR_SECRET_TOKEN_HERE'  # Оставь как есть, если B12 пропущен, или замени на свой токен
WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbwyFOdcITCcIecR-kN7RLO4GnwDn6tqGYa2a64kcMa4YLunOESDZ6NV2hIZWaEv0cq2pw/exec"

def send_google_log(store, cat):
    """IMP-05: неблокирующая отправка лога в daemon-потоке.
    Если поток не успеет завершиться — лог теряется, но скрипт не зависает."""
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