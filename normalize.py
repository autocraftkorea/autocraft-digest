import pandas as pd
from datetime import datetime
import json, os, re

KCAR_GRADE_MAP = {'A1':9,'A2':8,'A3':7,'A4':6,'A6':5,'A7':4,'B1':6,'B2':5,'B6':3,'B7':3,'C1':4,'C2':3,'D1':2,'F1':2,'F2':1,'F5':1}
AUTOHUB_GRADE_MAP = {'AA':10,'AB':9,'AC':8,'AD':7,'AF':6,'BA':8,'BB':7,'BC':6,'BD':5,'BF':5,'CA':6,'CB':5,'CC':4,'CD':3,'CF':3,'DA':4,'DB':3,'DC':2,'FA':2,'FB':2,'FC':1,'FF':1}
FUEL_MAP_KCAR = {'가솔린':'gasoline','디젤':'diesel','LPG':'lpg','가솔린+전기':'hybrid','가솔린+LPG':'lpg','전기':'ev'}
FUEL_MAP_AUTOHUB = {'가솔린':'gasoline','디젤':'diesel','LPG':'lpg','하이브리드':'hybrid','전기':'ev','수소':'hydrogen','겸용':'other'}
TRANSMISSION_MAP = {'오토':'auto','수동':'manual','세미오토':'semi_auto'}
USAGE_MAP_KCAR = {'상품':'personal','자가':'personal','렌트':'rental'}
USAGE_MAP_AUTOHUB = {'자가용':'personal','렌터카':'rental','영업용':'commercial','업무용':'business'}

def parse_mileage(val):
    if val is None: return None
    if isinstance(val,(int,float)): return int(val)
    cleaned = str(val).replace(',','').replace('km','').replace('Km','').strip()
    try: return int(float(cleaned))
    except: return None

def parse_date(val):
    if val is None: return None
    if isinstance(val,datetime): return val.strftime('%Y-%m-%d')
    try:
        s = str(val).strip().replace('-','').replace('.','')[:8]
        if len(s)==8 and s.isdigit(): return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    except: pass
    return None

def parse_make(name):
    if not name or str(name)=='nan': return None
    parts = str(name).strip().split()
    return parts[0] if parts else None

def parse_model(name):
    if not name or str(name)=='nan': return None
    parts = str(name).strip().split()
    return parts[1] if len(parts)>=2 else None

def parse_year_from_title(s):
    m = re.search(r'\(20(\d{2})\)', str(s))
    if m: return int('20'+m.group(1))
    m = re.search(r'\b(20\d{2})\b', str(s))
    return int(m.group(1)) if m else None

def check_no_accident(val):
    if not val or str(val)=='nan': return None
    return str(val).strip()=='무사고'

def normalise_kcar(filepath):
    print(f"\n[K-Car] Reading: {filepath}")
    df = pd.read_csv(filepath, encoding='utf-8-sig', header=26, dtype=str, on_bad_lines='skip', engine='python')
    col_names = ['lane','lot','location','name','reg_no','price','first_reg','mileage','transmission','fuel','color','accident_exchange','accident_repair','exterior_panels','notes','usage','grade','parking']
    current = list(df.columns)
    for i,n in enumerate(col_names):
        if i < len(current): current[i] = n
    df.columns = current
    print(f"[K-Car] Raw rows: {len(df)}")
    records = []
    for _,row in df.iterrows():
        lot = str(row.get('lot','')).strip()
        if not lot or lot=='nan': continue
        price_raw = str(row.get('price','')).strip().replace(',','')
        try: starting_price = int(float(price_raw)) if price_raw and price_raw!='nan' else None
        except: starting_price = None
        name_str = str(row.get('name','')).strip()
        model_year = parse_year_from_title(name_str)
        first_reg = parse_date(row.get('first_reg'))
        if model_year is None and first_reg:
            try: model_year = int(first_reg[:4])
            except: pass
        grade_raw = str(row.get('grade','')).strip()
        fuel_raw = str(row.get('fuel','')).strip()
        exchange_raw = str(row.get('accident_exchange','')).strip()
        exterior_raw = str(row.get('exterior_panels','')).replace('판','').strip()
        exterior_count = int(exterior_raw) if exterior_raw.isdigit() else None
        records.append({
            'source_platform':'kcar','source_record_id':f"kcar_{lot}",
            'lot_number':lot,'auction_lane':str(row.get('lane','')).strip() or None,
            'auction_location':str(row.get('location','')).strip() or None,
            'parking_location':str(row.get('parking','')).strip() or None,
            'starting_price_krw':starting_price,'full_vehicle_name':name_str or None,
            'make':parse_make(name_str),'model':parse_model(name_str),
            'model_year':model_year,'first_registration_date':first_reg,
            'registration_number':str(row.get('reg_no','')).strip() or None,
            'mileage_km':parse_mileage(row.get('mileage')),'mileage_unknown':False,
            'fuel_type':FUEL_MAP_KCAR.get(fuel_raw,'other'),
            'transmission':TRANSMISSION_MAP.get(str(row.get('transmission','')).strip(),None),
            'color':str(row.get('color','')).strip() or None,
            'usage_type':USAGE_MAP_KCAR.get(str(row.get('usage','')).strip(),'personal'),
            'platform_grade':grade_raw,'normalised_grade':KCAR_GRADE_MAP.get(grade_raw,None),
            'accident_panels_exchanged':exchange_raw or None,
            'accident_panels_repaired':str(row.get('accident_repair','')).strip() or None,
            'exterior_panel_count':exterior_count,'no_accident':check_no_accident(exchange_raw),
            'special_notes':str(row.get('notes','')).strip() or None,
            'lien_count':None,'mortgage_count':None,'flood_history':None,'vin':None,
            'ingested_at':datetime.utcnow().isoformat(),
            'source_file':os.path.basename(filepath),'detail_page_fetched':False
        })
    print(f"[K-Car] Normalised records: {len(records)}")
    return records

def normalise_autohub(filepath):
    print(f"\n[Autohub] Reading: {filepath}")
    df = pd.read_excel(filepath, engine='openpyxl', dtype=str)
    print(f"[Autohub] Raw rows: {len(df)}")
    records = []
    for _,row in df.iterrows():
        lot = str(row.get('출품번호','')).strip()
        if not lot or lot=='nan': continue
        grade_raw = str(row.get('평가등급','')).strip()
        soh_raw = str(row.get('SOH','')).strip()
        try: battery_soh = float(soh_raw) if soh_raw not in ('nan','','None') else None
        except: battery_soh = None
        price_raw = row.get('시작가(만원)','')
        try:
            price_val = float(str(price_raw).strip().replace(',',''))
            starting_price = int(price_val*10000) if price_val else None
        except: starting_price = None
        mileage_raw = row.get('주행거리','')
        try: mileage = int(float(str(mileage_raw).strip())) if str(mileage_raw).strip() not in ('nan','') else None
        except: mileage = None
        lane_raw = str(row.get('경매레인','')).strip()
        lane = lane_raw.replace('레인','').replace(' ','').strip() or None
        year_raw = str(row.get('연식','')).strip()
        try: model_year = int(year_raw[:4]) if year_raw and year_raw!='nan' else None
        except: model_year = None
        records.append({
            'source_platform':'autohub','source_record_id':f"autohub_{lot}",
            'lot_number':lot,'auction_lane':lane,'auction_location':'Anseong',
            'parking_location':str(row.get('주차번호','')).strip() or None,
            'starting_price_krw':starting_price,
            'full_vehicle_name':str(row.get('차명','')).strip() or None,
            'make':parse_make(row.get('차명')),'model':parse_model(row.get('차명')),
            'model_year':model_year,'first_registration_date':parse_date(row.get('최초등록일')),
            'registration_number':str(row.get('차량번호','')).strip() or None,
            'mileage_km':mileage,'mileage_unknown':str(row.get('주행거리불명','N')).strip()=='Y',
            'fuel_type':FUEL_MAP_AUTOHUB.get(str(row.get('연료','')).strip(),'other'),
            'transmission':TRANSMISSION_MAP.get(str(row.get('변속기','')).strip(),None),
            'color':str(row.get('색상','')).strip() or None,
            'usage_type':USAGE_MAP_AUTOHUB.get(str(row.get('차량경력','')).strip(),'personal'),
            'platform_grade':grade_raw,'normalised_grade':AUTOHUB_GRADE_MAP.get(grade_raw,None),
            'accident_panels_exchanged':None,'accident_panels_repaired':None,
            'exterior_panel_count':None,'no_accident':None,'special_notes':None,
            'lien_count':None,'mortgage_count':None,'flood_history':None,'vin':None,
            'battery_soh_pct':battery_soh,'ingested_at':datetime.utcnow().isoformat(),
            'source_file':os.path.basename(filepath),'detail_page_fetched':False
        })
    print(f"[Autohub] Normalised records: {len(records)}")
    return records

if __name__=='__main__':
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),'data')
    kcar_files = [f for f in os.listdir(data_dir) if f.startswith('KCAR_') and f.endswith('.csv')]
    autohub_files = [f for f in os.listdir(data_dir) if f.endswith('.xlsx') and not f.startswith('WEEKLY') and not f.startswith('KCAR')]
    all_records = []
    for f in kcar_files:
        all_records.extend(normalise_kcar(os.path.join(data_dir,f)))
    for f in autohub_files:
        all_records.extend(normalise_autohub(os.path.join(data_dir,f)))
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),'normalised_vehicles.json')
    with open(output_path,'w',encoding='utf-8') as f:
        json.dump(all_records,f,ensure_ascii=False,indent=2,default=str)
    print(f"\n✓ Done — {len(all_records)} total records")
    print(f"✓ Saved to: {output_path}")
    kcar_count = sum(1 for r in all_records if r['source_platform']=='kcar')
    autohub_count = sum(1 for r in all_records if r['source_platform']=='autohub')
    graded = sum(1 for r in all_records if r['normalised_grade'] is not None)
    print(f"\nSummary:\n  K-Car vehicles:    {kcar_count}\n  Autohub vehicles:  {autohub_count}\n  Grade mapped:      {graded}")
    print(f"\nSample — first 3 records:")
    for r in all_records[:3]:
        price_str = f"₩{r['starting_price_krw']:,}" if r['starting_price_krw'] else "TBD"
        print(f"\n  [{r['source_platform'].upper()}] {r['full_vehicle_name']}")
        print(f"    Grade: {r['platform_grade']} → {r['normalised_grade']}/10")
        print(f"    Year: {r['model_year']}  Mileage: {r['mileage_km']}km  Price: {price_str}")
        print(f"    Fuel: {r['fuel_type']}  Trans: {r['transmission']}  Usage: {r['usage_type']}")
        print(f"    No accident: {r['no_accident']}")
