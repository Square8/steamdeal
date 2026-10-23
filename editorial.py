import json
from datetime import date, datetime, timezone
import config


def fresh_observation(value, today: date) -> bool:
    if not isinstance(value, str):
        return False
    try:
        checked = date.fromisoformat(value)
    except ValueError:
        return False
    return (checked.isoformat() == value
            and 0 <= (today - checked).days <= config.EDITORIAL_MAX_PRICE_AGE_DAYS)

def generate_picks(games: list[dict], base_url: str, now: datetime | None = None) -> str:
    """
    GameDil 편집 추천 후보 JSON 생성.
    
    [스키마]
    schema_version: 1
    generated_at: 생성 시각(UTC, ISO format)
    wednesday: 수요일 추천 후보 목록 (최대 12개)
    saturday: 토요일 추천 후보 목록 (최대 12개)
    
    [항목]
    appid, name, url, price_current, discount_pct, is_free, korean, has_demo, 
    review_count, review_positive_pct, price_checked_at(유료 실제 관측일 price_last),
    availability_checked_at(무료 상태 등 마지막 상세 조회일), reviews_checked_at, reasoning_code
    freshness_policy: UTC 기준일/허용 날짜 차이/신선도 제외 수(요일별 조건 적용 전)
    
    [공통 조건]
    - adult 제외, coming_soon 제외
    - app_type == 'game' 만 허용 (DLC, 데모 등 제외)
    - appid 필수
    - 유료 게임은 양수의 price_final 필요 (결측치 0원 추정 불가)
    - review_total(또는 review_count), review_positive_pct 등 유효한 평가 상태 필요 (None은 무효)
    - 유료 price_last / 무료 checked_at의 UTC 날짜 차이 0~EDITORIAL_MAX_PRICE_AGE_DAYS
    - 결측/오류/미래 날짜 제외. 후보 부족 시 오래된 데이터로 보충하지 않음.
    
    [수요일 조건: 가격·할인 중심]
    - 유료 (is_free False 또는 0)
    - 할인 중 (discount_pct > 0)
    - 긍정률 80% 이상
    - 리뷰 50개 이상
    - 정렬: 할인율 높은 순 -> 추천 점수 높은 순 -> appid
    
    [토요일 조건: 취향·플레이 특징 중심]
    - 긍정률 80% 이상
    - 리뷰 50개 이상
    - 정렬: 한국어 우선 -> 데모 우선 -> 추천 점수 높은 순 -> appid
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    today = now.date()
    excluded_stale = 0
    valid_games = []
    for g in games:
        appid = g.get("appid")
        if not appid:
            continue
        if g.get("adult") or g.get("coming_soon"):
            continue
        if g.get("app_type") != "game":
            continue
            
        # Check valid price state
        price = g.get("price_final")
        is_free = g.get("is_free")
        
        if is_free:
            pass # Free games are allowed on Saturday
        elif price is None or price <= 0:
            continue # Paid games must have positive price
            
        # Check valid review state
        reviews = g.get("review_total") if g.get("review_total") is not None else g.get("review_count")
        pos_pct = g.get("review_positive_pct")
        if reviews is None or pos_pct is None:
            continue

        # JSON 생성 시각은 게임별 가격 확인일을 대신할 수 없다.
        # 무료는 가격 이력이 없으므로 상세 조회로 확인한 무료 상태의 날짜를 쓴다.
        checked = g.get("checked_at") if is_free else g.get("price_last")
        if not fresh_observation(checked, today):
            excluded_stale += 1
            continue
            
        valid_games.append(g)

    # Wednesday candidates
    wed_cands = []
    for g in valid_games:
        is_free = g.get("is_free")
        discount = g.get("discount_pct") or 0
        reviews = g.get("review_total") if g.get("review_total") is not None else g.get("review_count")
        pos_pct = g.get("review_positive_pct") or 0
        
        if not is_free and discount > 0 and pos_pct >= 80 and reviews >= 50:
            wed_cands.append(g)
            
    # Sort Wed: korean (1/0), -discount_pct, -score, appid
    wed_cands.sort(key=lambda x: (
        -1 if x.get("korean") else 0,
        -(x.get("discount_pct") or 0), 
        -(x.get("score") or 0), 
        x["appid"]
    ))
    wed_cands = wed_cands[:12]
    
    # Saturday candidates
    sat_cands = []
    for g in valid_games:
        reviews = g.get("review_total") if g.get("review_total") is not None else g.get("review_count")
        pos_pct = g.get("review_positive_pct") or 0
        
        if pos_pct >= 80 and reviews >= 50:
            sat_cands.append(g)
            
    # Sort Sat: korean (1/0), demo (1/0), -score, appid
    sat_cands.sort(key=lambda x: (
        -1 if x.get("korean") else 0,
        -1 if (x.get("has_demo") or x.get("app_type") == "demo") else 0,
        -(x.get("score") or 0),
        x["appid"]
    ))
    sat_cands = sat_cands[:12]
    
    def format_item(g, reasoning):
        base = base_url if base_url else ""
        return {
            "appid": g["appid"],
            "name": g.get("name"),
            "url": f"{base}/game/{g['appid']}.html",
            "price_current": g.get("price_final"),
            "discount_pct": g.get("discount_pct"),
            "is_free": bool(g.get("is_free")),
            "korean": bool(g.get("korean")),
            "has_demo": bool(g.get("has_demo") or g.get("app_type") == "demo"),
            "review_count": g.get("review_total") if g.get("review_total") is not None else g.get("review_count"),
            "review_positive_pct": g.get("review_positive_pct"),
            "price_checked_at": None if g.get("is_free") else g.get("price_last"),
            "availability_checked_at": g.get("checked_at"),
            "reviews_checked_at": g.get("reviews_checked_at"),
            "reasoning_code": reasoning
        }

    out = {
        "schema_version": 1,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "freshness_policy": {
            "max_age_days": config.EDITORIAL_MAX_PRICE_AGE_DAYS,
            "date_basis": "UTC", "evaluated_on": today.isoformat(),
            "excluded_stale_count": excluded_stale,
        },
        "wednesday": [format_item(g, "wed_discount") for g in wed_cands],
        "saturday": [format_item(g, "sat_features") for g in sat_cands]
    }
    
    return json.dumps(out, ensure_ascii=False, separators=(',', ':'))
