import csv
import re
from datetime import datetime, timedelta

file_path = r'c:\Users\Administrator\Desktop\Trabalho\ERP Talatto\backend\pedidos_2026-05-02.csv'

def parse_date(date_str):
    try:
        # 2026-04-01 09:53:15.643893+00:00
        return datetime.strptime(date_str.split('+')[0], '%Y-%m-%d %H:%M:%S.%f')
    except:
        try:
            return datetime.strptime(date_str.split('+')[0], '%Y-%m-%d %H:%M:%S')
        except:
            return None

def analyze_gaps(file_path):
    all_rows = []
    with open(file_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            nfe = row.get('numero_nf')
            dt = parse_date(row.get('criado_em', ''))
            all_rows.append({
                'id': row.get('id', 'N/A'),
                'numero_nf': int(nfe) if nfe and nfe.isdigit() else None,
                'criado_em': row.get('criado_em', 'N/A'),
                'dt': dt,
                'vendedor': row.get('id_vendedor', 'N/A'),
                'situacao': row.get('situacao', 'N/A'),
                'modelo': row.get('modelo_fiscal', 'N/A'),
                'xml': row.get('xml_autorizado', '')
            })

    # Filter only rows with NFe
    nfe_rows = [r for r in all_rows if r['numero_nf'] is not None]
    nfe_rows.sort(key=lambda x: x['numero_nf'])

    gaps = []
    for i in range(1, len(nfe_rows)):
        if nfe_rows[i]['numero_nf'] - nfe_rows[i-1]['numero_nf'] > 1:
            gaps.append((nfe_rows[i-1], nfe_rows[i]))

    print(f"Total gaps: {len(gaps)}\n")

    for prev, curr in gaps:
        gap_start = prev['numero_nf'] + 1
        gap_end = curr['numero_nf'] - 1
        print(f"--- GAP {gap_start} to {gap_end} ---")
        print(f"Before: ID={prev['id']}, NFe={prev['numero_nf']}, Created={prev['criado_em']}, Seller={prev['vendedor']}")
        print(f"After:  ID={curr['id']}, NFe={curr['numero_nf']}, Created={curr['criado_em']}, Seller={curr['vendedor']}")
        
        # Find orders created around the same time
        if prev['dt'] and curr['dt']:
            start_window = min(prev['dt'], curr['dt']) - timedelta(seconds=10)
            end_window = max(prev['dt'], curr['dt']) + timedelta(seconds=10)
            
            concurrent = [r for r in all_rows if r['dt'] and start_window <= r['dt'] <= end_window]
            if concurrent:
                print(f"  Orders created in time window ({start_window.time()} - {end_window.time()}):")
                for r in sorted(concurrent, key=lambda x: x['dt']):
                    marker = " -> GAP" if r['id'] in [prev['id'], curr['id']] else ""
                    print(f"    - ID: {r['id']}, NFe: {r['numero_nf']}, Created: {r['dt'].time()}, Status: {r['situacao']}{marker}")
        
        # Find sequential IDs
        try:
            prev_id = int(prev['id'])
            curr_id = int(curr['id'])
            id_range = range(min(prev_id, curr_id)-2, max(prev_id, curr_id)+3)
            seq_ids = [r for r in all_rows if r['id'].isdigit() and int(r['id']) in id_range]
            if seq_ids:
                print(f"  Orders with sequential IDs ({min(id_range)} - {max(id_range)}):")
                for r in sorted(seq_ids, key=lambda x: int(x['id'])):
                    marker = " -> GAP" if r['id'] in [prev['id'], curr['id']] else ""
                    print(f"    - ID: {r['id']}, NFe: {r['numero_nf']}, Created: {r['dt'].time() if r['dt'] else 'N/A'}, Status: {r['situacao']}{marker}")
        except:
            pass
        print("\n")

if __name__ == "__main__":
    analyze_gaps(file_path)
