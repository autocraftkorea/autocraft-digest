import json
import os
from datetime import datetime

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def passes_hard_filters(v, p):
    if p.get("source_platforms") and v["source_platform"] not in p["source_platforms"]:
        return False, ["platform not in scope"]
    if p.get("makes"):
        if not v.get("make") or not any(m in str(v["make"]) for m in p["makes"]):
            return False, ["make not in criteria"]
    if p.get("models"):
        name = str(v.get("full_vehicle_name") or "")
        if not any(m in name for m in p["models"]):
            return False, ["model not in criteria"]
    if p.get("fuel_types") and v.get("fuel_type") not in p["fuel_types"]:
        return False, ["fuel type excluded"]
    if p.get("transmissions") and v.get("transmission") not in p["transmissions"]:
        return False, ["transmission excluded"]
    if p.get("model_year_min") and v.get("model_year"):
        if v["model_year"] < p["model_year_min"]:
            return False, ["year below minimum"]
    if p.get("model_year_max") and v.get("model_year"):
        if v["model_year"] > p["model_year_max"]:
            return False, ["year above maximum"]
    if p.get("mileage_max_km") and v.get("mileage_km") is not None:
        if v["mileage_km"] > p["mileage_max_km"]:
            return False, ["mileage too high"]
    if p.get("price_max_krw") and v.get("starting_price_krw") is not None:
        if v["starting_price_krw"] > p["price_max_krw"]:
            return False, ["price above budget"]
    if p.get("grade_min") and v.get("normalised_grade") is not None:
        if v["normalised_grade"] < p["grade_min"]:
            return False, ["grade below minimum"]
    if v.get("lien_count") is not None and v["lien_count"] > p.get("max_lien_count", 0):
        return False, ["lien present"]
    if v.get("mortgage_count") is not None and v["mortgage_count"] > p.get("max_mortgage_count", 0):
        return False, ["mortgage present"]
    if not p.get("flood_history_allowed", False):
        if v.get("flood_history") and v["flood_history"] not in ("none", None):
            return False, ["flood history present"]
    if p.get("exclude_rental") and v.get("usage_type") == "rental":
        return False, ["rental excluded"]
    if p.get("exclude_commercial") and v.get("usage_type") in ("commercial", "business"):
        return False, ["commercial use excluded"]
    if p.get("exclude_accident") and v.get("no_accident") is False:
        return False, ["accident history present"]
    if p.get("colors_excluded") and v.get("color"):
        if any(c in str(v["color"]) for c in p["colors_excluded"]):
            return False, ["colour excluded"]
    if p.get("keyword_excludes") and v.get("special_notes"):
        notes = str(v["special_notes"])
        for kw in p["keyword_excludes"]:
            if kw in notes:
                return False, [f"keyword excluded: {kw}"]
    return True, []

def score_vehicle(v, p):
    current_year = datetime.now().year
    grade = v.get("normalised_grade")
    grade_min = p.get("grade_min", 1)
    grade_pref = p.get("grade_preferred_min", grade_min)
    if grade is None:
        grade_score = 0.5
    elif grade >= grade_pref:
        grade_score = 1.0
    elif grade >= grade_min:
        grade_score = 0.5 + ((grade - grade_min) / (grade_pref - grade_min)) * 0.5 if grade_pref > grade_min else 1.0
    else:
        grade_score = 0.0

    mileage = v.get("mileage_km")
    mileage_target = p.get("mileage_target_km")
    mileage_max = p.get("mileage_max_km")
    if mileage is None or mileage_target is None:
        mileage_score = 0.5
    elif mileage <= mileage_target:
        mileage_score = 1.0
    elif mileage_max and mileage_max > mileage_target:
        mileage_score = max(0.0, 1.0 - (mileage - mileage_target) / (mileage_max - mileage_target))
    else:
        mileage_score = 0.0

    price = v.get("starting_price_krw")
    price_target = p.get("price_target_krw")
    price_max = p.get("price_max_krw")
    if price is None or price == 0 or price_target is None:
        price_score = 0.5
    elif price <= price_target:
        price_score = 1.0
    elif price_max and price_max > price_target:
        price_score = max(0.0, 1.0 - (price - price_target) / (price_max - price_target))
    else:
        price_score = 0.0

    year = v.get("model_year")
    year_min = p.get("model_year_min")
    if year is None or year_min is None:
        year_score = 0.5
    else:
        denom = current_year - year_min
        year_score = max(0.0, min(1.0, (year - year_min) / denom)) if denom > 0 else 1.0

    no_accident_pref = p.get("no_accident_preferred", False)
    w_accident = p.get("weight_accident", 5)
    if not no_accident_pref or w_accident == 0:
        accident_score = 0.0
        w_accident = 0
    else:
        accident_score = 1.0 if v.get("no_accident") is True else 0.0

    w_grade   = p.get("weight_grade", 35)
    w_mileage = p.get("weight_mileage", 25)
    w_price   = p.get("weight_price", 20)
    w_year    = p.get("weight_year", 15)
    total_w   = w_grade + w_mileage + w_price + w_year + w_accident

    match_score = (
        grade_score   * w_grade +
        mileage_score * w_mileage +
        price_score   * w_price +
        year_score    * w_year +
        accident_score * w_accident
    ) / total_w if total_w > 0 else 0.0

    breakdown = {
        "grade":    round(grade_score, 3),
        "mileage":  round(mileage_score, 3),
        "price":    round(price_score, 3),
        "year":     round(year_score, 3),
        "accident": round(accident_score, 3)
    }
    return round(match_score, 4), breakdown

def generate_flags(v, p, breakdown):
    flags = []
    if v.get("no_accident") is True:
        flags.append("no accident")
    if breakdown["grade"] >= 1.0:
        flags.append(f"grade: {v.get('platform_grade','')} ({v.get('normalised_grade')}/10)")
    if breakdown["mileage"] >= 1.0 and v.get("mileage_km") is not None:
        flags.append("mileage at or below target")
    if breakdown["price"] >= 1.0 and v.get("starting_price_krw"):
        flags.append("price at or below target")
    if p.get("colors_preferred") and v.get("color"):
        if any(c in str(v["color"]) for c in p["colors_preferred"]):
            flags.append("preferred colour")
    if breakdown["grade"] < 1.0 and breakdown["grade"] >= 0.5:
        flags.append("grade below preferred")
    if breakdown["mileage"] < 1.0 and breakdown["mileage"] > 0:
        flags.append("mileage above target")
    if breakdown["price"] < 1.0 and breakdown["price"] > 0:
        flags.append("price above target")
    if v.get("no_accident") is False and p.get("no_accident_preferred"):
        flags.append("accident history")
    if v.get("usage_type") == "rental":
        flags.append("rental history")
    if v.get("mileage_unknown"):
        flags.append("mileage unknown")
    if p.get("keyword_flags") and v.get("special_notes"):
        notes = str(v["special_notes"])
        for kw in p["keyword_flags"]:
            if kw in notes:
                flags.append(f"keyword: {kw}")
    flags.append(f"from {v['source_platform']}")
    return flags

def listing_url(v):
    lot = v.get("lot_number", "")
    if v["source_platform"] == "kcar":
        return f"https://www.kcarauction.com/auction/{lot}"
    elif v["source_platform"] == "autohub":
        return f"https://www.sellcarauction.co.kr/auction/detail/{lot}"
    return ""

if __name__ == "__main__":
    base     = os.path.dirname(os.path.abspath(__file__))
    vehicles = load_json(os.path.join(base, "normalised_vehicles.json"))
    profiles = load_json(os.path.join(base, "profiles.json"))
    print(f"Loaded {len(vehicles)} vehicles, {len(profiles)} profiles")

    all_results = []

    for profile in profiles:
        if not profile.get("profile_active", True):
            continue
        pid   = profile["profile_id"]
        pname = profile["customer_name"]
        passed = []

        for v in vehicles:
            ok, _ = passes_hard_filters(v, profile)
            if not ok:
                continue
            score, breakdown = score_vehicle(v, profile)
            if score < profile.get("near_miss_threshold", 0.40):
                continue
            flags = generate_flags(v, profile, breakdown)
            is_near_miss = score < profile.get("near_miss_label_threshold", 0.70)
            passed.append({
                "profile_id": pid, "customer_name": pname,
                "source_record_id": v["source_record_id"],
                "lot_number": v["lot_number"],
                "source_platform": v["source_platform"],
                "ingested_at": v.get("ingested_at"),
                "auction_lane": v.get("auction_lane"),
                "parking_location": v.get("parking_location"),
                "full_vehicle_name": v.get("full_vehicle_name"),
                "model_year": v.get("model_year"),
                "mileage_km": v.get("mileage_km"),
                "starting_price_krw": v.get("starting_price_krw"),
                "platform_grade": v.get("platform_grade"),
                "normalised_grade": v.get("normalised_grade"),
                "fuel_type": v.get("fuel_type"),
                "transmission": v.get("transmission"),
                "color": v.get("color"),
                "usage_type": v.get("usage_type"),
                "no_accident": v.get("no_accident"),
                "special_notes": v.get("special_notes"),
                "match_score": score,
                "score_breakdown": breakdown,
                "flags": flags,
                "is_near_miss": is_near_miss,
                "listing_url": listing_url(v),
                "matched_at": datetime.utcnow().isoformat()
            })

        passed.sort(key=lambda x: x["match_score"], reverse=True)
        passed = passed[:profile.get("max_results_per_digest", 10)]

        strong = sum(1 for r in passed if not r["is_near_miss"])
        near   = sum(1 for r in passed if r["is_near_miss"])
        print(f"\n[{pname}]")
        print(f"  In digest: {len(passed)} | Strong: {strong} | Near-miss: {near}")
        if passed:
            top = passed[0]
            price_str = f"W{top['starting_price_krw']:,}" if top["starting_price_krw"] else "TBD"
            print(f"  Top: {str(top['full_vehicle_name'])[:55]}")
            print(f"       Score:{top['match_score']} Grade:{top['platform_grade']} {top['mileage_km']}km {price_str}")

        all_results.extend(passed)

    out = os.path.join(base, "match_results.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nDone — {len(all_results)} results saved to match_results.json")