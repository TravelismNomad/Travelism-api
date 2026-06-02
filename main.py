from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os

from supabase import create_client, Client

app = FastAPI(title="Travelism API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY", "")

def get_db() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ══════════════════════════════════════════
# МОДЕЛИ ДАННЫХ
# ══════════════════════════════════════════

class ProfileModel(BaseModel):
    telegram_id: int
    first_name: Optional[str] = None
    phone: Optional[str] = None
    citizenship: Optional[str] = None
    departure_city: Optional[str] = None
    language: Optional[str] = "ru"

class TripModel(BaseModel):
    telegram_id: int
    destination_city: str
    destination_country: str
    destination_emoji: Optional[str] = "🌍"
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    adults: int = 1
    children: int = 0
    budget: Optional[float] = None
    flight_url: Optional[str] = None
    hotel_url: Optional[str] = None
    plan_summary: Optional[str] = None

class PlaceModel(BaseModel):
    name: str
    category: Optional[str] = "cafe"
    country: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    instagram_url: Optional[str] = None
    maps_url: Optional[str] = None
    description: Optional[str] = None
    halal_friendly: Optional[bool] = False
    family_friendly: Optional[bool] = False
    submitted_by: Optional[int] = None

class ReviewModel(BaseModel):
    place_id: int
    telegram_id: int
    rating: int
    comment: Optional[str] = None


# ══════════════════════════════════════════
# ГЛАВНАЯ СТРАНИЦА
# ══════════════════════════════════════════

@app.get("/")
def root():
    return {
        "status": "✅ Travelism API работает",
        "version": "1.0.0",
        "endpoints": [
            "GET  /api/profile/{telegram_id}",
            "POST /api/profile",
            "GET  /api/trips/{telegram_id}",
            "POST /api/trips",
            "GET  /api/places",
            "POST /api/places",
            "POST /api/reviews",
            "POST /api/points",
        ]
    }


# ══════════════════════════════════════════
# ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ
# ══════════════════════════════════════════

@app.post("/api/profile")
def save_profile(data: ProfileModel):
    db = get_db()
    try:
        existing = db.table("users")\
            .select("telegram_id, points")\
            .eq("telegram_id", data.telegram_id)\
            .execute()

        profile_dict = {k: v for k, v in data.dict().items() if v is not None}

        if existing.data:
            # Обновить существующий профиль
            result = db.table("users")\
                .update(profile_dict)\
                .eq("telegram_id", data.telegram_id)\
                .execute()
            message = "Профиль обновлён"
        else:
            # Создать новый + бонус за регистрацию
            profile_dict["points"] = 30
            profile_dict["level"] = 1
            profile_dict["suitcase_pct"] = 20
            profile_dict["trips_count"] = 0
            result = db.table("users")\
                .insert(profile_dict)\
                .execute()
            message = "Профиль создан +30 XP"

        return {"success": True, "message": message}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/profile/{telegram_id}")
def get_profile(telegram_id: int):
    db = get_db()
    try:
        result = db.table("users")\
            .select("*")\
            .eq("telegram_id", telegram_id)\
            .execute()

        if not result.data:
            raise HTTPException(status_code=404, detail="Профиль не найден")

        profile = result.data[0]

        # Добавить название уровня
        pts = profile.get("points", 0)
        level_names = {
            1: "🌱 Новичок",
            2: "✈️ Турист",
            3: "🗺 Исследователь",
            4: "🧭 Номад",
            5: "🏆 Travel Master",
            6: "🌍 Global Citizen",
        }
        profile["level_name"] = level_names.get(profile.get("level", 1), "🌱 Новичок")

        return profile
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════
# ПОЕЗДКИ
# ══════════════════════════════════════════

@app.post("/api/trips")
def save_trip(data: TripModel):
    db = get_db()
    try:
        trip_dict = {k: v for k, v in data.dict().items() if v is not None}
        result = db.table("trips").insert(trip_dict).execute()

        # Начислить +10 XP за поездку
        _add_points_internal(db, data.telegram_id, 10)

        return {
            "success": True,
            "trip_id": result.data[0]["id"] if result.data else None,
            "message": "+10 XP начислено"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/trips/{telegram_id}")
def get_trips(telegram_id: int, limit: int = 10):
    db = get_db()
    try:
        result = db.table("trips")\
            .select("*")\
            .eq("telegram_id", telegram_id)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()

        return {"trips": result.data, "count": len(result.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════
# МЕСТА (маркетплейс)
# ══════════════════════════════════════════

@app.get("/api/places")
def get_places(
    city: Optional[str] = None,
    country: Optional[str] = None,
    category: Optional[str] = None,
    halal: Optional[bool] = None,
    limit: int = 20
):
    db = get_db()
    try:
        query = db.table("places")\
            .select("*")\
            .eq("status", "approved")

        if city:
            query = query.ilike("city", f"%{city}%")
        if country:
            query = query.ilike("country", f"%{country}%")
        if category:
            query = query.eq("category", category)
        if halal is not None:
            query = query.eq("halal_friendly", halal)

        result = query.order("rating_avg", desc=True).limit(limit).execute()
        return {"places": result.data, "count": len(result.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/places")
def add_place(data: PlaceModel):
    db = get_db()
    try:
        place_dict = {k: v for k, v in data.dict().items() if v is not None}
        place_dict["status"] = "pending"
        result = db.table("places").insert(place_dict).execute()

        return {
            "success": True,
            "message": "Заявка принята на проверку. Мы свяжемся с вами."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════
# ОТЗЫВЫ
# ══════════════════════════════════════════

@app.post("/api/reviews")
def add_review(data: ReviewModel):
    db = get_db()
    try:
        if data.rating < 1 or data.rating > 5:
            raise HTTPException(status_code=400, detail="Рейтинг должен быть от 1 до 5")

        review_dict = {k: v for k, v in data.dict().items() if v is not None}
        db.table("reviews").insert(review_dict).execute()

        # Пересчитать средний рейтинг места
        all_reviews = db.table("reviews")\
            .select("rating")\
            .eq("place_id", data.place_id)\
            .execute()

        if all_reviews.data:
            avg = sum(r["rating"] for r in all_reviews.data) / len(all_reviews.data)
            db.table("places")\
                .update({
                    "rating_avg": round(avg, 1),
                    "reviews_count": len(all_reviews.data)
                })\
                .eq("id", data.place_id)\
                .execute()

        # Начислить +15 XP за отзыв
        _add_points_internal(db, data.telegram_id, 15)

        return {"success": True, "message": "+15 XP за отзыв"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/places/{place_id}/reviews")
def get_reviews(place_id: int):
    db = get_db()
    try:
        result = db.table("reviews")\
            .select("*")\
            .eq("place_id", place_id)\
            .order("created_at", desc=True)\
            .execute()

        return {"reviews": result.data, "count": len(result.data)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ══════════════════════════════════════════
# ГЕЙМИФИКАЦИЯ
# ══════════════════════════════════════════

def _add_points_internal(db: Client, telegram_id: int, points: int):
    """Внутренняя функция начисления баллов"""
    try:
        existing = db.table("users")\
            .select("points")\
            .eq("telegram_id", telegram_id)\
            .execute()

        if not existing.data:
            return

        current = existing.data[0]["points"] or 0
        new_points = current + points

        # Определить уровень
        level = 1
        if new_points >= 500:   level = 2
        if new_points >= 1500:  level = 3
        if new_points >= 3000:  level = 4
        if new_points >= 5000:  level = 5
        if new_points >= 15000: level = 6

        db.table("users")\
            .update({"points": new_points, "level": level})\
            .eq("telegram_id", telegram_id)\
            .execute()
    except:
        pass


@app.post("/api/points")
def add_points(telegram_id: int, points: int, reason: str = ""):
    db = get_db()
    try:
        existing = db.table("users")\
            .select("points, level")\
            .eq("telegram_id", telegram_id)\
            .execute()

        if not existing.data:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        current = existing.data[0]["points"] or 0
        new_points = current + points

        level = 1
        if new_points >= 500:   level = 2
        if new_points >= 1500:  level = 3
        if new_points >= 3000:  level = 4
        if new_points >= 5000:  level = 5
        if new_points >= 15000: level = 6

        level_names = {
            1:"🌱 Новичок", 2:"✈️ Турист", 3:"🗺 Исследователь",
            4:"🧭 Номад", 5:"🏆 Travel Master", 6:"🌍 Global Citizen"
        }

        db.table("users")\
            .update({"points": new_points, "level": level})\
            .eq("telegram_id", telegram_id)\
            .execute()

        return {
            "success": True,
            "points": new_points,
            "level": level,
            "level_name": level_names[level],
            "added": points,
            "reason": reason
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/leaderboard")
def get_leaderboard(limit: int = 10):
    db = get_db()
    try:
        result = db.table("users")\
            .select("first_name, points, level, trips_count")\
            .order("points", desc=True)\
            .limit(limit)\
            .execute()

        return {"leaderboard": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
