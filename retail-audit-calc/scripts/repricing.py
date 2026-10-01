import os, glob, json, subprocess, pandas as pd

def main():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Склеиваем продажи G1 и G2
    sales_p1 = os.path.join(base, 'sales.xlsx')
    sales_p2 = os.path.join(base, 'sales_g2.xlsx')
    
    dfs = []
    if os.path.exists(sales_p1): dfs.append(pd.read_excel(sales_p1, header=1))
    if os.path.exists(sales_p2): dfs.append(pd.read_excel(sales_p2, header=1))
    df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    
    for c in ['Цена закупки', 'Цена продажи', 'Количество']:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            
    df['join_key'] = df['Наименование'].astype(str).str.strip().str.lower()
    
    # Каталоги
    cat_files = glob.glob(os.path.join(base, '*catalog*.xlsx'))
    if cat_files:
        try:
            df_c = pd.concat([pd.read_excel(f) for f in cat_files], ignore_index=True)
            df_c.columns = [str(c).strip() for c in df_c.columns]
            name_c = next((c for c in df_c.columns if any(k in c.lower() for k in ['наимен', 'номенкл', 'sku', 'товар'])), df_c.columns[0])
            df_c = df_c.rename(columns={name_c: 'cat_name'})
            df_c['join_key'] = df_c['cat_name'].astype(str).str.strip().str.lower()
            df = pd.merge(df, df_c.drop_duplicates(subset=['join_key']), on='join_key', how='left')
        except: pass

    df = df[df['Цена закупки'] > 0].copy()
    df['Наценка'] = ((df['Цена продажи'] - df['Цена закупки']) / df['Цена закупки'] * 100)
    low = df[df['Наценка'] < 35].copy()

    str_cols = [c for c in low.columns if low[c].dtype == 'object' and c not in ['join_key', 'cat_name']]
    mask_exc = low[str_cols].apply(lambda col: col.astype(str).str.contains('сергей|рыба', case=False, na=False)).any(axis=1)
    fish_kw = 'св,?яр|лещ|судак|карась|сазан|толстолоб|жерех|вомер|окунь|густера|забан|мойва|плотва|скумбри|сельдь|иваси|вобла|синец|х/?к|г/?к|вял'
    mask_exc = mask_exc | low['Наименование'].astype(str).str.contains('св,?яр', case=False, na=False) | (low['Наименование'].astype(str).str.contains(fish_kw, case=False, na=False) & (low['Наценка'].abs() < 0.01))
    low = low[~mask_exc].copy()

    SHORT_M = {'ВОЗДУШНАЯ': 'ВОЗД', 'ЭНГЕЛЬСА': 'ЭНГ', 'СИДОРОВА': 'СИД', 'НИКИТИНА': 'НИК', 'ВЛКСМ': 'ВЛКСМ', 'ПОРТ': 'ПОРТ', 'САНАТОРНАЯ': 'САНАТ', 'ПОКУПАЛКА': 'ПОКУП', 'ШТЕМЕНКО': 'ШТЕМ', 'РОДНИКОВАЯ': 'РОДН', 'Батова': 'БАТ', 'КАЛАЧ': 'КАЛАЧ', 'КОТЕЛЬНИКОВО': 'КОТ'}
    
    def compress_stores(st_list):
        st = sorted(set(st_list))
        if len(st) >= 13: return 'ВСЯ СЕТЬ'
        if len(st) >= 5: return f'Сеть ({len(st)} точ.)'
        return ', '.join([SHORT_M.get(s, s) for s in st])

    g = low.groupby('Наименование').agg(
        Кол=('Количество', 'sum'),
        Выручка=('Цена продажи', 'sum'),
        Себестоимость=('Цена закупки', 'sum'),
        Точек=('МАГАЗИН', 'nunique'),
        Магазины_сжатые=('МАГАЗИН', compress_stores),
        Магазины_полные=('МАГАЗИН', lambda x: ', '.join(sorted(x.unique())))
    ).reset_index()

    g['Наценка_итог'] = ((g['Выручка'] - g['Себестоимость']) / g['Себестоимость'] * 100).round(1)
    g = g.sort_values('Наценка_итог', ascending=True)

    out_file = 'reestr_pereocenka.xlsx'
    export_df = g[['Наименование', 'Кол', 'Выручка', 'Себестоимость', 'Наценка_итог', 'Точек', 'Магазины_полные']].copy()
    export_df.columns = ['Наименование SKU', 'Продажи', 'Выручка', 'Себестоимость', 'Наценка %', 'Точек', 'Магазины']
    export_df.to_excel(out_file, index=False)

    up = subprocess.run(['dify-agent', 'file', 'upload', out_file], capture_output=True, text=True)
    download_link = ''
    try:
        p_url = json.loads(up.stdout).get('public_download_url', '')
        if p_url: download_link = 'https://difyretail.ru' + p_url
    except: pass

    print(f'КЛИКАБЕЛЬНАЯ_ССЫЛКА|{download_link}')
    print(f'ИТОГО_РЕЕСТР|{len(g)}|{int(g["Выручка"].sum())}|{int(g["Себестоимость"].sum())}')
    for i, (_, r) in enumerate(g.head(20).iterrows(), 1):
        name = (r['Наименование'][:33] + '..') if len(r['Наименование']) > 35 else r['Наименование']
        print(f"{i}|{name}|{r['Наценка_итог']}%|{r['Магазины_сжатые']}")

if __name__ == '__main__':
    main()