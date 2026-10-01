import os, re, json, subprocess
import urllib.request
import urllib.parse
import pandas as pd

def norm(s):
    return re.sub(r'\s+', ' ', str(s).strip().lower().replace('"', '').replace("'", ''))

def shorten_url(long_url):
    if not long_url:
        return ''
    try:
        api_url = "https://tinyurl.com/api-create.php?url=" + urllib.parse.quote(long_url)
        req = urllib.request.Request(api_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4) as response:
            res = response.read().decode('utf-8').strip()
            if res.startswith('http'):
                return res
    except Exception:
        pass
    return long_url

STOP_WORDS = {
    'пиво', 'светлое', 'темное', 'фильтрованное', 'нефильтрованное', 'пастеризованное',
    'непастеризованное', '0.45', '0.45л', '0.5', '0.5л', '1л', 'чипсы', 'снеки', 'пэт', 
    'вес', 'шт', 'в', 'ассортименте', 'напиток', 'живое'
}

def check_group(sales_file, cat_file, label, base_dir):
    sp = os.path.join(base_dir, sales_file)
    cp = os.path.join(base_dir, cat_file)
    
    if not os.path.exists(sp) or not os.path.exists(cp):
        return None

    s = pd.read_excel(sp, header=1)
    s.columns = [str(c).strip() for c in s.columns]
    s['Количество'] = pd.to_numeric(s['Количество'], errors='coerce').fillna(0)
    sold = s[s['Количество'] > 0].copy()
    sold['k'] = sold['Наименование'].map(norm)

    c = pd.read_excel(cp)
    c.columns = [str(c).strip() for c in c.columns]
    c['k'] = c['Наименование'].map(norm)
    cat_set = set(c['k'])

    missing = sold[~sold['k'].isin(cat_set)]
    agg = missing.groupby('Наименование').agg(
        Кол=('Количество', 'sum'),
        Маг=('МАГАЗИН', 'nunique'),
        Магазины=('МАГАЗИН', lambda x: ', '.join(sorted(x.unique())))
    ).sort_values('Кол', ascending=False).reset_index()

    def find_fuzzy(n):
        toks = set(norm(n).split()) - STOP_WORDS
        if not toks:
            toks = set(norm(n).split())
        for cn in cat_set:
            ct = set(cn.split()) - STOP_WORDS
            if not ct:
                ct = set(cn.split())
            intersection = len(toks & ct)
            union = len(toks | ct)
            if union > 0 and (intersection / union) >= 0.7:
                return cn
        return None

    agg['Похожее_в_каталоге'] = agg['Наименование'].map(find_fuzzy)
    agg['Тип_ошибки'] = agg['Похожее_в_каталоге'].apply(lambda x: 'Разное написание / опечатка' if x else 'Полностью отсутствует')
    agg['Группа_файлов'] = label

    real_cnt = (agg['Тип_ошибки'] == 'Полностью отсутствует').sum()
    fuzzy_cnt = (agg['Тип_ошибки'] != 'Полностью отсутствует').sum()

    print(f"RES|{label}|Всего_продаж:{len(sold)}|В_каталоге:{len(c)}|Нет_в_каталоге:{len(agg)}|Реально_нет:{real_cnt}|Разное_написание:{fuzzy_cnt}|Объем_потерь:{round(agg['Кол'].sum(),1)}")
    
    return agg

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    all_diffs = []
    
    res1 = check_group('sales.xlsx', 'catalog.xlsx', 'G1', base_dir)
    if res1 is not None: all_diffs.append(res1)
    
    res2 = check_group('sales_g2.xlsx', 'catalog_g2.xlsx', 'G2', base_dir)
    if res2 is not None: all_diffs.append(res2)

    short_link = ''
    if all_diffs:
        full_df = pd.concat(all_diffs, ignore_index=True)
        
        # Печатаем ТОП-15 позиций расхождений гарантированно (по продажам)
        top15 = full_df.sort_values('Кол', ascending=False).head(15)
        for _, r in top15.iterrows():
            print(f"MISS|{r['Группа_файлов']}|{r['Наименование']}|{round(r['Кол'],1)}|точек:{r['Маг']}")

        out_file = 'reestr_otstutstvuyushchih_sku.xlsx'
        export_df = full_df[['Группа_файлов', 'Наименование', 'Тип_ошибки', 'Похожее_в_каталоге', 'Кол', 'Маг', 'Магазины']].copy()
        export_df.columns = ['Группа', 'Наименование в продажах', 'Статус', 'Похожее в каталоге (1С)', 'Объем продаж', 'Кол-во точек', 'Список магазинов']
        export_df.to_excel(out_file, index=False)
        
        up = subprocess.run(['dify-agent', 'file', 'upload', out_file], capture_output=True, text=True)
        try:
            p_url = json.loads(up.stdout).get('public_download_url', '')
            if p_url:
                raw_url = 'https://difyretail.ru' + p_url
                short_link = shorten_url(raw_url)
        except Exception:
            pass

    print(f"КЛИКАБЕЛЬНАЯ_ССЫЛКА|{short_link}")

if __name__ == '__main__':
    main()