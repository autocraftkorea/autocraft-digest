"""Deterministic Korean->English translation for auction vehicle names.

Vehicle names decompose into make + model + trim tokens drawn from a bounded
vocabulary (Korean car trims are a finite set). We translate by dictionary
lookup rather than machine translation so the pipeline stays offline, free and
reproducible. Coverage target is ~95% of tokens; any token not in the
dictionary is left as-is (still readable, just untranslated).

Only the display name is translated. The original Korean `full_vehicle_name`
is preserved for the matching engine, whose profile rules are Korean.
"""
import re

# --- Multi-word phrases (translated before single tokens) ---
PHRASES = {
    "세부등급 없음": "(no sub-grade)",
    "세부등급없음": "(no sub-grade)",
    "일반인 판매용": "public sale",
    "(일반인 판매용)": "(public sale)",
    "(다이내믹 5링크)": "(Dynamic 5-Link)",
}

# --- Makes ---
MAKES = {
    "쉐보레(GM대우)": "Chevrolet (GM Daewoo)",
    "르노코리아(삼성)": "Renault Korea (Samsung)",
    "현대": "Hyundai", "기아": "Kia", "제네시스": "Genesis",
    "쉐보레": "Chevrolet", "르노코리아": "Renault Korea",
    "벤츠": "Mercedes-Benz", "폭스바겐": "Volkswagen", "미니": "MINI",
    "아우디": "Audi", "포드": "Ford", "닛산": "Nissan", "렉서스": "Lexus",
    "혼다": "Honda", "지프": "Jeep", "링컨": "Lincoln", "도요타": "Toyota",
    "재규어": "Jaguar", "캐딜락": "Cadillac", "테슬라": "Tesla",
    "푸조": "Peugeot", "랜드로버": "Land Rover", "인피니티": "Infiniti",
    "볼보": "Volvo",
}

# --- Models (incl. trim-like model variants) ---
MODELS = {
    "그랜저": "Grandeur", "아반떼": "Avante", "쏘나타": "Sonata",
    "쏘렌토": "Sorento", "스포티지": "Sportage", "싼타페": "Santa Fe",
    "투싼": "Tucson", "스파크": "Spark", "카니발": "Carnival",
    "뉴모닝": "New Morning", "모닝": "Morning", "스타렉스": "Starex",
    "레이": "Ray", "포터2": "Porter II", "포터": "Porter",
    "봉고III": "Bongo III", "봉고": "Bongo", "니로": "Niro",
    "뉴코란도": "New Korando", "코란도": "Korando", "티볼리": "Tivoli",
    "모하비": "Mohave", "팰리세이드": "Palisade", "올란도": "Orlando",
    "트랙스": "Trax", "크루즈": "Cruze", "말리부": "Malibu",
    "렉스턴": "Rexton", "프라이드(신형)": "Pride (new)", "프라이드": "Pride",
    "아이오닉": "Ioniq", "쏘울": "Soul", "포르테": "Forte",
    "캡티바": "Captiva", "코나": "Kona", "벨로스터": "Veloster",
    "알티마": "Altima", "셀토스": "Seltos", "맥스크루즈": "Maxcruz",
    "캐스퍼": "Casper", "스타리아": "Staria", "트레일블레이저": "Trailblazer",
    "파사트": "Passat", "체로키": "Cherokee", "티구안": "Tiguan",
    "제타": "Jetta", "캠리": "Camry", "프리우스": "Prius",
    "임팔라": "Impala", "스토닉": "Stonic", "베라크루즈": "Veracruz",
    "머스탱": "Mustang", "마티즈": "Matiz", "로체": "Lotze",
    "마스터즈": "Masters", "마스터": "Master", "e-마이티": "e-Mighty",
    "마이티": "Mighty", "메가트럭": "Mega Truck", "에쿠스(신형)": "Equus (new)",
    "에쿠스": "Equus", "디스커버리": "Discovery", "익스플로러": "Explorer",
    "에비에이터": "Aviator", "노틸러스": "Nautilus", "에스컬레이드": "Escalade",
    "올뉴어코드": "All New Accord", "재즈": "Jazz", "씨티": "City",
    "베르나(신형)": "Verna (new)", "베르나": "Verna",
    "엑센트(신형)": "Accent (new)", "엑센트": "Accent",
    "워크스루밴": "Walk-through Van", "타스만": "Tasman",
    "클럽맨": "Clubman", "컨트리맨": "Countryman", "쿠퍼": "Cooper",
    "뉴SM5(신형)": "New SM5 (new)", "뉴SM5": "New SM5", "뉴SM3": "New SM3",
    "뉴QM3": "New QM3", "베라크루즈": "Veracruz",
}

# --- Trim / spec / body-type vocabulary ---
TRIMS = {
    "그랜드": "Grand", "럭셔리": "Luxury", "프레스티지": "Prestige",
    "블랙프리미엄": "Black Premium", "프리미엄": "Premium", "터보": "Turbo",
    "스마트팩": "Smart Pack", "스마트": "Smart", "노블레스": "Noblesse",
    "노블": "Noble", "모던": "Modern", "기본형": "Base",
    "익스클루시브": "Exclusive", "스페셜": "Special", "하이브리드": "Hybrid",
    "가솔린+전기": "Gasoline+Electric", "가솔린": "Gasoline",
    "디젤(e-VGT)": "Diesel (e-VGT)", "디젤": "Diesel",
    "디럭스팩(블랙휠)": "Deluxe Pack (Black Wheel)", "디럭스팩": "Deluxe Pack",
    "디럭스": "Deluxe", "시그니처": "Signature", "초장축": "Extra-Long",
    "장축고상": "Long High-floor", "장축": "Long-wheelbase",
    "초이스": "Choice", "트렌디": "Trendy", "트랜디": "Trendy",
    "스포츠": "Sports", "최고급형": "Top-of-line", "고급형": "High-grade",
    "왜건": "Wagon", "웨건": "Wagon", "르블랑": "Le Blanc",
    "프리미어": "Premier", "프리미에르": "Premiere", "스타일": "Style",
    "넥스트": "Next", "플래티넘": "Platinum", "슈퍼캡": "Super Cab",
    "특장": "Special-purpose", "캘리그래피": "Calligraphy",
    "인스퍼레이션": "Inspiration", "래더패키지": "Ladder Package",
    "패키지": "Package", "컨비니언스팩": "Convenience Pack",
    "세이프티팩": "Safety Pack", "세이프티": "Safety", "프라임": "Prime",
    "브라운에디션": "Brown Edition", "에디션": "Edition",
    "더블캡": "Double Cab", "킹캡(싱글컴프)": "King Cab (Single Comp)",
    "킹캡": "King Cab", "일반캡": "Standard Cab", "세단": "Sedan",
    "베스트셀렉션Ⅰ": "Best Selection I", "베스트셀렉션Ⅱ": "Best Selection II",
    "셀렉션Ⅰ": "Selection I", "롱레인지": "Long Range", "레인지": "Range",
    "브릴리언트": "Brilliant", "콰트로": "Quattro", "리미티드": "Limited",
    "어반": "Urban", "투리스모": "Turismo", "노바": "Nova",
    "어메이징": "Amazing", "밸류": "Value", "아머": "Armor",
    "패밀리": "Family", "일렉트리파이드": "Electrified",
    "일렉트릭": "Electric", "전기": "Electric", "그래비티": "Gravity",
    "스탠다드": "Standard", "하이냉동탑차": "High Freezer Truck",
    "냉동탑차": "Freezer Truck", "냉장탑차": "Chiller Truck",
    "다이나믹": "Dynamic", "다이내믹": "Dynamic", "패션": "Fashion",
    "골드": "Gold", "컴포트": "Comfort", "베스트": "Best", "어스": "Earth",
    "네오": "Neo", "바이퓨얼": "Bi-Fuel", "에어로": "Aero", "에어": "Air",
    "컬렉션": "Collection", "쿠페": "Coupe", "하이리무진": "High Limousine",
    "리무진": "Limousine", "기어": "Gear", "법인전용": "Corporate-only",
    "부스터": "Booster", "클래식": "Classic", "포트폴리오": "Portfolio",
    "윙바디": "Wing Body", "아방가르드": "Avantgarde", "익스트림": "Extreme",
    "블루모션": "BlueMotion", "블루세이버": "Blue Saver",
    "에센셜": "Essential", "블랙레이블": "Black Label", "레인저": "Ranger",
    "랩터": "Raptor", "서밋": "Summit", "리저브": "Reserve",
    "밀레니얼": "Millennial", "디자인": "Design", "퓨어": "Pure",
    "엑셀런스": "Excellence", "뷰티": "Beauty", "크리에이티브": "Creative",
    "시티팝": "City Pop", "파크": "Park", "이노베이션": "Innovation",
    "어드벤처": "Adventure", "유니크": "Unique", "살룬": "Saloon",
    "트랜스폼": "Transform", "해치백": "Hatchback", "퍼펙트": "Perfect",
    "볼드": "Bold", "레드라인": "Redline", "엔터테인먼트": "Entertainment",
    "조이": "Joy", "프로페셔널": "Professional", "프로": "Pro",
    "슈프림": "Supreme", "수출형": "Export", "에코": "Eco",
    "파워게이트": "Power Gate", "전동식": "Powered", "프레지던트": "President",
    "섀도우": "Shadow", "레이디": "Lady", "VIP팩": "VIP Pack",
    "메트로": "Metro", "워너비": "Wannabe", "테크": "Tech",
    "트윈컴프": "Twin Comp", "싱글컴프": "Single Comp", "오리지널": "Original",
    "컴팩트": "Compact", "에이스": "Ace", "클럽": "Club",
    "헤리티지": "Heritage", "엣지": "Edge", "라운지": "Lounge",
    "큐티": "Cutie", "슈퍼": "Super", "블랙": "Black", "스타": "Star",
    "플러스": "Plus", "트럭": "Truck", "렌터카": "rental", "투어러": "Tourer",
    "엘레강스": "Elegance", "베리": "Very", "클러비": "Clubby",
    "모델": "Model", "볼트": "Bolt", "카고": "Cargo", "패밀리": "Family",
    "장애인용": "Disabled-access", "신형": "New", "마력": "hp",
    "N라인": "N Line", "라인": "Line", "하이": "High", "로열": "Royal",
    "로얄": "Royal", "칸": "Khan",
}

# Merge; longer keys must win, so we sort at match time.
_DICT = {}
for _d in (MAKES, MODELS, TRIMS):
    _DICT.update(_d)
_SORTED_KEYS = sorted(_DICT.keys(), key=len, reverse=True)

# Single-Hangul-char tokens: only replace when not glued to other Hangul,
# to avoid corrupting unmapped compound words.
_SINGLE = {"뉴": "New", "더": "The", "올": "All", "밴": "Van",
           "탑": "Top", "롱": "Long", "디": "D"}

_HANGUL = r"[가-힣]"

def _counted_units(s):
    s = re.sub(r"(\d+(?:\.\d+)?)\s*톤", r"\1-ton", s)
    s = re.sub(r"(\d+)\s*인승", r"\1-seater", s)
    s = re.sub(r"\(\s*(\d+)\s*세대\s*\)", r"(Gen \1)", s)
    s = re.sub(r"(\d+)\s*세대", r"Gen \1", s)
    s = re.sub(r"(\d+)\s*도어", r"\1-door", s)
    s = re.sub(r"(\d+)\s*시리즈", r"\1 Series", s)
    s = re.sub(r"(\d+)\s*링크", r"\1-Link", s)
    return s

def translate_name(name):
    if not name:
        return name
    s = str(name)
    # 1) multi-word phrases
    for ko, en in PHRASES.items():
        s = s.replace(ko, en)
    # 2) counted units (N-ton, N-seater, Gen N, N-door, N Series)
    s = _counted_units(s)
    # 3) X-클래스 -> X-Class
    s = s.replace("클래스", "Class")
    # 4) dictionary, longest key first
    for ko in _SORTED_KEYS:
        if ko in s:
            s = s.replace(ko, _DICT[ko])
    # 5) single-char tokens, boundary-protected
    for ko, en in _SINGLE.items():
        s = re.sub(f"(?<!{_HANGUL}){ko}(?!{_HANGUL})", en, s)
    # 6) tidy whitespace
    s = re.sub(r"\s+", " ", s).strip()
    return s


if __name__ == "__main__":
    import json, os, re as _re
    base = os.path.dirname(os.path.abspath(__file__))
    norm = json.load(open(os.path.join(base, "normalised_vehicles.json"), encoding="utf-8"))
    han = _re.compile(r"[가-힣]")
    names = sorted(set(str(v.get("full_vehicle_name") or "") for v in norm))
    untranslated = 0
    residual = {}
    for n in names:
        t = translate_name(n)
        if han.search(t):
            untranslated += 1
            for tok in t.split():
                for ch in tok:
                    if han.match(ch):
                        residual[tok] = residual.get(tok, 0) + 1
                        break
    print(f"Distinct names: {len(names)} | names with residual Korean: {untranslated}")
    print("Sample translations:")
    for n in names[:25]:
        print(f"  {n}\n    -> {translate_name(n)}")
    if residual:
        print("\nResidual Korean tokens (uncovered):")
        for tok, c in sorted(residual.items(), key=lambda x: -x[1]):
            print(f"  {c}\t{tok}")
