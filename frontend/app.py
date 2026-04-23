# -*- coding: utf-8 -*-
import base64
import calendar
import datetime as dt
import html
import os
import random
import re
import sys
from pathlib import Path
from urllib.parse import quote

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import requests
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from config.settings import NUTRISEEKER_API_URL

API_URL = (NUTRISEEKER_API_URL or "http://localhost:8000").rstrip("/")

from database.user_store import (
    append_history_entry,
    create_user,
    get_user_by_email,
    init_db,
    update_profile_guidance,
    update_user_identity,
    verify_user,
)

ICON_PATH = APP_DIR / "assets" / "nutriseeker_icon.svg"
CALORIE_GOAL = 2000
MACRO_GOALS = {"protein": 120, "carbs": 220, "fat": 65}
EMAIL_PATTERN = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)


def load_icon_svg() -> str:
    if ICON_PATH.exists():
        return ICON_PATH.read_text(encoding="utf-8")
    return """
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128">
      <defs>
        <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="#69D36E"/>
          <stop offset="100%" stop-color="#2E7D32"/>
        </linearGradient>
      </defs>
      <rect width="128" height="128" rx="30" fill="#F4F8F2"/>
      <path d="M62 28c-18 10-29 28-29 45 0 16 11 29 31 29 8 0 17-3 24-9 5-5 9-12 10-21-9 5-17 7-23 7-14 0-23-10-23-23 0-10 4-19 10-28Z" fill="url(#g)"/>
      <path d="M85 25c-4 22-16 36-35 46 5 6 13 10 23 10 15 0 27-12 27-29 0-11-5-20-15-27Z" fill="#97E08C"/>
      <circle cx="70" cy="40" r="7" fill="#F6B73C"/>
    </svg>
    """


ICON_SVG = load_icon_svg()
ICON_URI = f"data:image/svg+xml;utf8,{quote(ICON_SVG)}"

st.set_page_config(
    page_title="NutriSeeker",
    page_icon="🥗",
    layout="wide",
    initial_sidebar_state="collapsed",
)

init_db()


def init_state() -> None:
    defaults = {
        "portion_grams": 150,
        "logged_in": False,
        "guest_mode": False,
        "active_screen": "Login",
        "display_name": "Alex",
        "pending_email": "",
        "current_user_id": None,
        "current_user_email": "",
        "onboarding_step": 1,
        "analysis_history": [],
        "latest_analysis": None,
        "selected_date": dt.date.today(),
        "display_month": dt.date.today().replace(day=1),
        "home_search": "",
        "profile_age": None,
        "profile_gender": "",
        "profile_height_cm": None,
        "profile_weight_kg": None,
        "profile_activity": "Moderate",
        "profile_goal": "Maintain",
        "profile_ready": False,
        "mobile_menu_open": False,
        "profile_avatar": "",
        "profile_flash": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    requested_screen = st.query_params.get("screen")
    allowed_screens = {"Login", "Onboarding", "Home", "Diary", "Results", "Insights", "Profile", "Add"}
    if requested_screen in allowed_screens:
        st.session_state.active_screen = requested_screen
    else:
        st.query_params["screen"] = st.session_state.active_screen


init_state()


def on_slider_change() -> None:
    st.session_state.portion_grams = st.session_state._slider_val


def on_input_change() -> None:
    value = st.session_state._input_val
    if value is None:
        value = 0
    st.session_state.portion_grams = max(0, min(1000, int(value)))


def set_screen(screen: str) -> None:
    st.session_state.active_screen = screen
    st.query_params["screen"] = screen


def navigate_to(screen: str) -> None:
    st.session_state.mobile_menu_open = False
    if screen == "Login":
        clear_user_session()
    set_screen(screen)


def go_to_brand_home() -> None:
    set_screen("Home" if has_authenticated_user() or st.session_state.guest_mode else "Login")


def route_options() -> list[tuple[str, str]]:
    if st.session_state.guest_mode and not has_authenticated_user():
        return [
            ("Login", "Sign In"),
            ("Home", "Home"),
        ]
    return [
        ("Login", "Sign In"),
        ("Home", "Home"),
        ("Diary", "Diary"),
        ("Results", "Results"),
        ("Insights", "Insights"),
        ("Profile", "Profile"),
    ]


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_PATTERN.match((email or "").strip()))


def default_avatar_specs() -> list[dict]:
    return [
        {"id": "ava", "name": "Ava", "kind": "human", "bg": "linear-gradient(180deg, #dff5ff, #c8e8ff)", "skin": "#F2C4A5", "hair": "#47322A", "shirt": "#5B88FF", "accent": "#D8E5FF"},
        {"id": "noah", "name": "Noah", "kind": "human", "bg": "linear-gradient(180deg, #e8f7df, #cdeebf)", "skin": "#E5B58D", "hair": "#2F2E41", "shirt": "#48A467", "accent": "#D9F4DF"},
        {"id": "zuri", "name": "Zuri", "kind": "human", "bg": "linear-gradient(180deg, #fff0d9, #ffd6a7)", "skin": "#8C5A43", "hair": "#2A1A18", "shirt": "#FF9D57", "accent": "#FFE8CB"},
        {"id": "kai", "name": "Kai", "kind": "human", "bg": "linear-gradient(180deg, #efe3ff, #dcc9ff)", "skin": "#D7A07D", "hair": "#5C3B7D", "shirt": "#7D6BFF", "accent": "#ECE5FF"},
        {"id": "lina", "name": "Lina", "kind": "human", "bg": "linear-gradient(180deg, #ffe4ec, #ffcddd)", "skin": "#E3B192", "hair": "#8A4A5F", "shirt": "#F86B8F", "accent": "#FFE8F0"},
        {"id": "bear", "name": "Bear", "kind": "bear", "bg": "linear-gradient(180deg, #ffe8d8, #ffd2b0)", "fur": "#8B5A3B", "shirt": "#66B56A", "accent": "#FFF0E3"},
        {"id": "fox", "name": "Fox", "kind": "fox", "bg": "linear-gradient(180deg, #fff2d6, #ffe2a7)", "fur": "#F08B3D", "shirt": "#4B9F76", "accent": "#FFF6E8"},
        {"id": "panda", "name": "Panda", "kind": "panda", "bg": "linear-gradient(180deg, #eef1f7, #dfe6f4)", "fur": "#F8FBFF", "shirt": "#5E7CE2", "accent": "#F3F6FB"},
    ]


AVATAR_SPECS = default_avatar_specs()
AVATAR_IDS = [spec["id"] for spec in AVATAR_SPECS]
AVATAR_LOOKUP = {spec["id"]: spec for spec in AVATAR_SPECS}
AVATAR_EMOJI = {
    "ava": "👩",
    "noah": "👨",
    "zuri": "🧑",
    "kai": "🧑‍💻",
    "lina": "👩‍🦰",
    "bear": "🐻",
    "fox": "🦊",
    "panda": "🐼",
}


def month_shift(base_date: dt.date, step: int) -> dt.date:
    year = base_date.year + ((base_date.month - 1 + step) // 12)
    month = ((base_date.month - 1 + step) % 12) + 1
    return dt.date(year, month, 1)


def portion_tag(grams: int) -> str:
    if grams <= 100:
        return "Small"
    if grams <= 250:
        return "Medium"
    if grams <= 500:
        return "Large"
    return "Extra Large"


def safe_food_title(item: dict) -> str:
    return clean_text(item.get("food", "Meal"), fallback="Meal").title()


def clean_text(value, fallback: str = "") -> str:
    text = re.sub(r"<[^>]+>", "", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text or fallback


def has_authenticated_user() -> bool:
    return bool(st.session_state.logged_in and st.session_state.current_user_id)


def empty_summary() -> dict:
    return {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0, "fiber": 0.0}


def render_empty_state_card(message: str, detail: str, *, icon: str = "🍽️", badge: str | None = None) -> None:
    badge_html = f'<span class="empty-state-badge">{html.escape(badge)}</span>' if badge else ""
    st.markdown(
        f"""
        <div class="empty-state-card">
            <div class="empty-state-icon" aria-hidden="true">{html.escape(icon)}</div>
            {badge_html}
            <h4>{html.escape(message)}</h4>
            <p>{html.escape(detail)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_recent_foods(foods: list[dict]) -> None:
    for start in range(0, len(foods), 4):
        row_items = foods[start : start + 4]
        row_columns = st.columns(len(row_items), gap="small")
        for column, food in zip(row_columns, row_items):
            name = clean_text(food.get("name"), fallback="Meal")
            meal_bucket = clean_text(food.get("meal_bucket"), fallback="Meal")
            date_text = clean_text(food.get("date"), fallback="")
            calories = float(food.get("calories", 0))
            initials = "".join(part[0] for part in name.split()[:2]).upper() or "NS"
            meta = f"{meal_bucket} · {date_text}" if date_text else meal_bucket
            with column:
                st.markdown('<div class="food-card">', unsafe_allow_html=True)
                st.markdown(f'<div class="food-thumb">{html.escape(initials)}</div>', unsafe_allow_html=True)
                st.markdown(f"**{name}**")
                st.caption(meta)
                st.markdown(f"**{calories:.0f} kcal**")
                st.markdown('</div>', unsafe_allow_html=True)


def render_meal_card(title: str, detail: str, calories: float) -> None:
    st.markdown(
        f"""
        <div class="meal-card">
            <div class="meal-row">
                <div class="meal-meta">
                    <h4>{html.escape(clean_text(title, fallback='Meal'))}</h4>
                    <p>{html.escape(clean_text(detail, fallback=''))}</p>
                </div>
                <div class="meal-kcal">{float(calories):.0f} kcal</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def summarize_results(results: list[dict]) -> dict:
    if not results:
        return {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0, "fiber": 0.0}
    return {
        "calories": sum(float(item.get("calories", 0)) for item in results),
        "protein": sum(float(item.get("protein", 0)) for item in results),
        "carbs": sum(float(item.get("carbs", 0)) for item in results),
        "fat": sum(float(item.get("fat", 0)) for item in results),
        "fiber": sum(float(item.get("fiber", 0)) for item in results),
    }


def macro_percentages(summary: dict) -> dict:
    protein = max(summary["protein"], 0)
    carbs = max(summary["carbs"], 0)
    fat = max(summary["fat"], 0)
    total = protein + carbs + fat
    if total <= 0:
        return {"protein": 0, "carbs": 0, "fat": 0}
    return {
        "protein": round((protein / total) * 100),
        "carbs": round((carbs / total) * 100),
        "fat": round((fat / total) * 100),
    }


def calorie_target_from_profile() -> float:
    if st.session_state.profile_height_cm in (None, "") or st.session_state.profile_weight_kg in (None, ""):
        return CALORIE_GOAL
    weight = float(st.session_state.profile_weight_kg)
    height = float(st.session_state.profile_height_cm)
    age = max(int(st.session_state.profile_age or 28), 1)
    gender = str(st.session_state.profile_gender or "").lower()
    if gender == "female":
        bmr = 10 * weight + 6.25 * height - 5 * age - 161
    elif gender == "male":
        bmr = 10 * weight + 6.25 * height - 5 * age + 5
    else:
        bmr = 10 * weight + 6.25 * height - 5 * age - 78
    activity_factor = {
        "Low": 1.2,
        "Moderate": 1.55,
        "High": 1.725,
    }.get(st.session_state.profile_activity, 1.55)
    target = bmr * activity_factor
    goal = st.session_state.profile_goal
    if goal == "Lose":
        target -= 350
    elif goal == "Gain":
        target += 300
    return max(target, 1200)


def bmi_snapshot() -> dict | None:
    height_cm = st.session_state.profile_height_cm
    weight_kg = st.session_state.profile_weight_kg
    if height_cm in (None, "") or weight_kg in (None, ""):
        return None
    height_m = float(height_cm) / 100
    if height_m <= 0:
        return None
    bmi = float(weight_kg) / (height_m * height_m)
    if bmi < 18.5:
        return {"bmi": bmi, "category": "Underweight", "label": "Needs attention", "icon": "🔵", "tone": "warning"}
    if bmi < 25:
        return {"bmi": bmi, "category": "Normal", "label": "Healthy range", "icon": "🟢", "tone": "success"}
    if bmi < 30:
        return {"bmi": bmi, "category": "Overweight", "label": "Above healthy range", "icon": "🟠", "tone": "warning"}
    return {"bmi": bmi, "category": "Obese", "label": "High risk range", "icon": "🔴", "tone": "error"}


def meal_quality(summary: dict) -> tuple[str, str]:
    protein = summary["protein"]
    fiber = summary["fiber"]
    calories = summary["calories"]
    fat = summary["fat"]
    if calories <= 0:
        return "No logged intake yet", "Log a meal to get quality feedback."
    if protein >= 20 and fiber >= 5 and fat <= 30:
        return "Balanced meal", "Good protein support with moderate fat and useful fiber."
    if fat > 35 and protein < 15:
        return "Heavier meal", "This looks more energy-dense and lower in protein balance."
    if calories < 250:
        return "Light meal", "Useful as a snack, but likely not enough as a full meal."
    return "Mixed nutrition profile", "The meal has useful energy, but macro balance could improve."


def explain_latest_analysis() -> list[str]:
    latest = st.session_state.latest_analysis
    summary = latest["summary"] if latest else {"calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0}
    target = calorie_target_from_profile()
    today_total = totals_for_day(dt.date.today())["calories"]
    bmi = bmi_snapshot()
    goal = st.session_state.profile_goal
    pct_today = 0 if target <= 0 else round((today_total / target) * 100)
    lines = []
    if bmi:
        lines.append(f"Your BMI is {bmi['bmi']:.1f} ({bmi['label']}).")
    else:
        lines.append("Add height and weight in Health Metrics to unlock BMI-based recommendations.")

    lines.append(f"You consumed {today_total:.0f} kcal today (~{pct_today}% of your daily target of {target:.0f} kcal).")

    if latest:
        foods = ", ".join(latest["foods"][:3])
        meal_pct = 0 if target <= 0 else round((summary["calories"] / target) * 100)
        quality_label, quality_detail = meal_quality(summary)
        lines.append(f"Latest analysis: {foods} contributed about {meal_pct}% of your daily target. {quality_label}: {quality_detail}")

    if 85 <= pct_today <= 105:
        lines.append("You are maintaining a balanced intake for today.")
    elif pct_today < 70:
        lines.append("Your intake is currently below target; consider adding one nutrient-dense meal or snack.")
    else:
        lines.append("Your intake is trending above target; a lighter next meal can improve balance.")

    protein_today = totals_for_day(dt.date.today())["protein"]
    if protein_today < MACRO_GOALS["protein"] * 0.7:
        lines.append("Consider adding more protein-rich foods for better muscle maintenance.")

    if goal == "Lose":
        lines.append("Your current goal is fat loss: prioritize high-fiber meals and lean protein while keeping calories controlled.")
    elif goal == "Gain":
        lines.append("Your current goal is muscle gain: maintain a calorie surplus with protein-rich meals across the day.")
    else:
        lines.append("Your current diet direction is aligned with your goal to maintain weight.")
    return lines


def random_avatar_id() -> str:
    return random.choice(AVATAR_IDS)


def ensure_avatar_selected() -> str:
    avatar_id = st.session_state.profile_avatar
    if avatar_id not in AVATAR_LOOKUP:
        avatar_id = random_avatar_id()
        st.session_state.profile_avatar = avatar_id
    return avatar_id


def render_human_avatar_svg(spec: dict) -> str:
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160">
      <defs>
        <linearGradient id="shirt-{spec['id']}" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="{spec['accent']}"/>
          <stop offset="100%" stop-color="{spec['shirt']}"/>
        </linearGradient>
        <linearGradient id="hair-{spec['id']}" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="{spec['hair']}"/>
          <stop offset="100%" stop-color="#1F1722"/>
        </linearGradient>
      </defs>
      <ellipse cx="80" cy="146" rx="42" ry="8" fill="rgba(24,36,29,0.10)"/>
      <path d="M41 130c6-24 24-38 39-38s33 14 39 38v12H41Z" fill="url(#shirt-{spec['id']})"/>
      <path d="M52 131c7-14 17-22 28-22 11 0 21 8 28 22" fill="none" stroke="rgba(255,255,255,0.35)" stroke-width="5" stroke-linecap="round"/>
      <path d="M48 60c0-23 15-39 33-39 19 0 33 16 33 39v7c0 8-3 15-8 21l-11-8H64l-9 8c-4-6-7-13-7-21Z" fill="url(#hair-{spec['id']})"/>
      <circle cx="80" cy="67" r="28" fill="{spec['skin']}"/>
      <path d="M56 54c2-16 13-28 24-28 14 0 27 10 30 27-4-7-10-12-18-13-11-2-24 4-36 14Z" fill="url(#hair-{spec['id']})"/>
      <circle cx="70" cy="67" r="2.6" fill="#2B211D"/>
      <circle cx="90" cy="67" r="2.6" fill="#2B211D"/>
      <path d="M72 79c5 4 11 4 16 0" fill="none" stroke="#9A5E4A" stroke-width="2.6" stroke-linecap="round"/>
      <path d="M63 96c4 7 10 10 17 10 7 0 13-3 17-10" fill="#F7E9DD"/>
      <circle cx="61" cy="73" r="4.2" fill="rgba(255,183,164,0.46)"/>
      <circle cx="99" cy="73" r="4.2" fill="rgba(255,183,164,0.46)"/>
    </svg>
    """


def render_bear_avatar_svg(spec: dict) -> str:
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160">
      <defs>
        <linearGradient id="bear-shirt-{spec['id']}" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="{spec['accent']}"/>
          <stop offset="100%" stop-color="{spec['shirt']}"/>
        </linearGradient>
      </defs>
      <ellipse cx="80" cy="146" rx="42" ry="8" fill="rgba(24,36,29,0.10)"/>
      <path d="M43 129c4-22 20-35 37-35s33 13 37 35v13H43Z" fill="url(#bear-shirt-{spec['id']})"/>
      <circle cx="58" cy="50" r="16" fill="{spec['fur']}"/>
      <circle cx="102" cy="50" r="16" fill="{spec['fur']}"/>
      <circle cx="80" cy="70" r="34" fill="{spec['fur']}"/>
      <ellipse cx="80" cy="81" rx="18" ry="14" fill="#F4D3BA"/>
      <circle cx="68" cy="69" r="3.5" fill="#34261E"/>
      <circle cx="92" cy="69" r="3.5" fill="#34261E"/>
      <path d="M73 88c4 4 10 4 14 0" fill="none" stroke="#6A4634" stroke-width="3" stroke-linecap="round"/>
      <ellipse cx="80" cy="79" rx="7" ry="5.5" fill="#6A4634"/>
    </svg>
    """


def render_fox_avatar_svg(spec: dict) -> str:
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160">
      <defs>
        <linearGradient id="fox-shirt-{spec['id']}" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="{spec['accent']}"/>
          <stop offset="100%" stop-color="{spec['shirt']}"/>
        </linearGradient>
      </defs>
      <ellipse cx="80" cy="146" rx="42" ry="8" fill="rgba(24,36,29,0.10)"/>
      <path d="M42 130c5-22 21-36 38-36s33 14 38 36v12H42Z" fill="url(#fox-shirt-{spec['id']})"/>
      <path d="M54 54l18-18 8 18Z" fill="{spec['fur']}"/>
      <path d="M106 54L88 36l-8 18Z" fill="{spec['fur']}"/>
      <path d="M46 72c0-22 15-38 34-38s34 16 34 38c0 20-15 34-34 34S46 92 46 72Z" fill="{spec['fur']}"/>
      <path d="M55 84c8-16 17-23 25-23s17 7 25 23c-8 10-16 15-25 15S63 94 55 84Z" fill="#FFF2E1"/>
      <circle cx="69" cy="72" r="3.2" fill="#35251E"/>
      <circle cx="91" cy="72" r="3.2" fill="#35251E"/>
      <path d="M74 84c4 4 8 4 12 0" fill="none" stroke="#6A4634" stroke-width="2.7" stroke-linecap="round"/>
      <circle cx="80" cy="79" r="4.5" fill="#6A4634"/>
    </svg>
    """


def render_panda_avatar_svg(spec: dict) -> str:
    return f"""
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160">
      <defs>
        <linearGradient id="panda-shirt-{spec['id']}" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stop-color="{spec['accent']}"/>
          <stop offset="100%" stop-color="{spec['shirt']}"/>
        </linearGradient>
      </defs>
      <ellipse cx="80" cy="146" rx="42" ry="8" fill="rgba(24,36,29,0.10)"/>
      <path d="M42 129c5-22 21-35 38-35s33 13 38 35v13H42Z" fill="url(#panda-shirt-{spec['id']})"/>
      <circle cx="58" cy="48" r="15" fill="#20262A"/>
      <circle cx="102" cy="48" r="15" fill="#20262A"/>
      <circle cx="80" cy="70" r="35" fill="{spec['fur']}"/>
      <ellipse cx="66" cy="70" rx="10" ry="13" fill="#20262A"/>
      <ellipse cx="94" cy="70" rx="10" ry="13" fill="#20262A"/>
      <circle cx="68" cy="70" r="3.1" fill="#FFFFFF"/>
      <circle cx="92" cy="70" r="3.1" fill="#FFFFFF"/>
      <ellipse cx="80" cy="84" rx="16" ry="12" fill="#DDE5EC"/>
      <circle cx="80" cy="80" r="4.8" fill="#20262A"/>
      <path d="M73 89c4 4 10 4 14 0" fill="none" stroke="#49555E" stroke-width="2.6" stroke-linecap="round"/>
    </svg>
    """


def avatar_svg_uri(avatar_id: str) -> str:
    spec = AVATAR_LOOKUP.get(avatar_id) or AVATAR_LOOKUP[random_avatar_id()]
    if spec["kind"] == "human":
        svg = render_human_avatar_svg(spec)
    elif spec["kind"] == "bear":
        svg = render_bear_avatar_svg(spec)
    elif spec["kind"] == "fox":
        svg = render_fox_avatar_svg(spec)
    else:
        svg = render_panda_avatar_svg(spec)
    return f"data:image/svg+xml;utf8,{quote(svg)}"


def avatar_emoji(avatar_id: str) -> str:
    return AVATAR_EMOJI.get(avatar_id, "🧑")


def render_avatar_image(avatar_id: str, *, width: int) -> None:
    font_size = max(48, int(width * 0.62))
    st.markdown(
        f"""
        <div style="display:flex;justify-content:center;">
            <div style="
                width:{width}px;
                height:{width}px;
                border-radius:999px;
                display:flex;
                align-items:center;
                justify-content:center;
                background:linear-gradient(180deg,#ffffff,#eef6ea);
                border:1px solid rgba(83,118,80,0.10);
                box-shadow:0 18px 34px rgba(46,125,50,0.10);
                font-size:{font_size}px;
                line-height:1;
            ">{avatar_emoji(avatar_id)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def avatar_markup(avatar_id: str, display_name: str, *, size: str = "profile", selected: bool = False, show_edit: bool = False) -> str:
    spec = AVATAR_LOOKUP.get(avatar_id) or AVATAR_LOOKUP[ensure_avatar_selected()]
    selection_class = " selected" if selected else ""
    overlay = '<div class="premium-avatar-edit">Edit</div>' if show_edit else ""
    return f"""
    <div class="premium-avatar premium-avatar-{size}{selection_class}">
        <div class="premium-avatar-orb" style="background:{spec['bg']};">
            <img class="premium-avatar-figure" src="{avatar_svg_uri(spec['id'])}" alt="{display_name} avatar" />
            {overlay}
        </div>
        <div class="premium-avatar-name">{spec['name']}</div>
    </div>
    """


def profile_tagline() -> str:
    if st.session_state.profile_goal == "Lose":
        return "Lighter decisions, smarter tracking, and steady consistency."
    if st.session_state.profile_goal == "Gain":
        return "Built to support stronger meals and better recovery."
    return "A polished nutrition companion for calmer daily choices."


def save_profile_identity(name: str, age: str | int | None, gender: str, avatar_id: str | None) -> None:
    clean_name = (name or "").strip() or "Alex"
    age_value = None
    if age not in (None, ""):
        try:
            age_value = max(1, int(age))
        except ValueError:
            age_value = None
    st.session_state.display_name = clean_name
    st.session_state.profile_age = age_value
    st.session_state.profile_gender = gender.strip()
    st.session_state.profile_avatar = avatar_id if avatar_id in AVATAR_LOOKUP else random_avatar_id()
    st.session_state.profile_ready = True
    if st.session_state.current_user_id:
        update_user_identity(
            st.session_state.current_user_id,
            st.session_state.display_name,
            st.session_state.profile_age,
            st.session_state.profile_gender,
            st.session_state.profile_avatar,
            st.session_state.profile_ready,
        )


def profile_snapshot() -> dict:
    return {
        "name": st.session_state.display_name or "Alex",
        "age": st.session_state.profile_age if st.session_state.profile_age is not None else "Not set",
        "gender": st.session_state.profile_gender or "Not set",
        "avatar": ensure_avatar_selected(),
    }


def load_user_into_session(bundle: dict) -> None:
    user = bundle.get("user") or {}
    profile = bundle.get("profile") or {}
    history = bundle.get("history") or []
    st.session_state.guest_mode = False
    st.session_state.current_user_id = user.get("id")
    st.session_state.current_user_email = user.get("email", "")
    st.session_state.pending_email = user.get("email", "")
    st.session_state.display_name = user.get("display_name", "Alex")
    st.session_state.profile_age = profile.get("age")
    st.session_state.profile_gender = profile.get("gender", "")
    st.session_state.profile_height_cm = profile.get("height_cm")
    st.session_state.profile_weight_kg = profile.get("weight_kg")
    st.session_state.profile_activity = profile.get("activity", "Moderate")
    st.session_state.profile_goal = profile.get("goal", "Maintain")
    st.session_state.profile_avatar = profile.get("avatar", "")
    st.session_state.profile_ready = bool(profile.get("profile_ready", 0))
    st.session_state.analysis_history = history
    st.session_state.latest_analysis = history[0] if history else None


def clear_user_session() -> None:
    st.session_state.logged_in = False
    st.session_state.guest_mode = False
    st.session_state.current_user_id = None
    st.session_state.current_user_email = ""
    st.session_state.pending_email = ""
    st.session_state.display_name = "Alex"
    st.session_state.analysis_history = []
    st.session_state.latest_analysis = None
    st.session_state.profile_age = None
    st.session_state.profile_gender = ""
    st.session_state.profile_height_cm = None
    st.session_state.profile_weight_kg = None
    st.session_state.profile_activity = "Moderate"
    st.session_state.profile_goal = "Maintain"
    st.session_state.profile_ready = False
    st.session_state.profile_avatar = ""
    st.session_state.onboarding_step = 1
    st.session_state.profile_flash = ""


def start_guest_mode() -> None:
    clear_user_session()
    st.session_state.guest_mode = True
    st.session_state.display_name = "Guest"
    st.session_state.active_screen = "Home"
    st.query_params["screen"] = "Home"


def render_image_preview(uploaded_file) -> None:
    image_bytes = uploaded_file.getvalue()
    image_uri = f"data:{uploaded_file.type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    st.markdown(
        f"""
        <div class="preview-shell screen-shell">
            <p class="preview-label">Meal Preview</p>
            <div class="preview-frame">
                <img src="{image_uri}" alt="Uploaded meal preview" />
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def meal_bucket(timestamp: dt.datetime) -> str:
    hour = timestamp.hour
    if hour < 11:
        return "Breakfast"
    if hour < 16:
        return "Lunch"
    if hour < 20:
        return "Snacks"
    return "Dinner"


def add_history_entry(data: dict, food_hint: str) -> None:
    now = dt.datetime.now()
    results = data.get("results", [])
    summary = summarize_results(results)
    foods = [safe_food_title(item) for item in results] or [food_hint.strip().title() or "Detected Meal"]
    entry = {
        "timestamp": now.isoformat(),
        "date": now.date().isoformat(),
        "meal_bucket": meal_bucket(now),
        "foods": foods,
        "raw_output": data.get("raw_output", ""),
        "grams": int(data.get("grams", st.session_state.portion_grams)),
        "results": results,
        "summary": summary,
    }
    st.session_state.latest_analysis = entry
    st.session_state.analysis_history.insert(0, entry)
    if st.session_state.current_user_id:
        append_history_entry(st.session_state.current_user_id, entry)


def explain_backend_response(response: requests.Response) -> str:
    text = (response.text or "").strip()
    content_type = response.headers.get("content-type", "").lower()
    if response.status_code == 501 or "text/html" in content_type or text.lower().startswith("<!doctype html"):
        return (
            f"NutriSeeker expected the FastAPI backend at `{API_URL}`, but that address returned an HTML "
            f"`{response.status_code}` response instead of the API. This usually means port 8000 is running the "
            f"wrong server. Start the backend with `uvicorn backend.main:app --host 0.0.0.0 --port 8000` or set "
            f"`NUTRISEEKER_API_URL` to the correct backend URL before launching Streamlit."
        )
    return f"Backend error ({response.status_code}): {text[:400]}"


def entries_for_day(day: dt.date) -> list[dict]:
    return [entry for entry in st.session_state.analysis_history if entry["date"] == day.isoformat()]


def totals_for_day(day: dt.date) -> dict:
    totals = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0, "fiber": 0.0}
    for entry in entries_for_day(day):
        for key in totals:
            totals[key] += float(entry["summary"].get(key, 0))
    return totals


def all_recent_foods() -> list[dict]:
    foods = []
    for entry in st.session_state.analysis_history:
        for item in entry["results"]:
            foods.append(
                {
                    "name": safe_food_title(item),
                    "calories": float(item.get("calories", 0)),
                    "meal_bucket": entry["meal_bucket"],
                    "date": entry["date"],
                }
            )
    return foods[:12]


def weekly_calorie_series() -> tuple[list[str], list[float]]:
    today = dt.date.today()
    labels = []
    values = []
    for offset in range(6, -1, -1):
        day = today - dt.timedelta(days=offset)
        labels.append(day.strftime("%a"))
        values.append(totals_for_day(day)["calories"])
    return labels, values


def render_calendar_html(selected_date: dt.date, display_month: dt.date) -> str:
    weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(display_month.year, display_month.month)
    month_entries = {
        entry["date"]: entry for entry in st.session_state.analysis_history if entry["date"].startswith(display_month.isoformat()[:7])
    }
    cells = []
    weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for day_name in weekdays:
        cells.append(f'<div class="calendar-weekday">{day_name}</div>')
    for week in weeks:
        for day in week:
            if day == 0:
                cells.append('<div class="calendar-day empty"></div>')
                continue
            cell_date = dt.date(display_month.year, display_month.month, day)
            is_selected = cell_date == selected_date
            has_data = cell_date.isoformat() in month_entries
            classes = ["calendar-day"]
            if is_selected:
                classes.append("selected")
            if has_data:
                classes.append("has-entry")
            dot = '<span class="calendar-dot"></span>' if has_data else ""
            cells.append(
                f'<div class="{" ".join(classes)}"><span>{day}</span>{dot}</div>'
            )
    return '<div class="calendar-grid">' + "".join(cells) + "</div>"


def render_progress_row(label: str, value: float, goal: float, color: str) -> None:
    percent = 0 if goal <= 0 else min(int((value / goal) * 100), 100)
    st.markdown(
        f"""
        <div class="macro-row">
            <div class="macro-row-head">
                <div>
                    <p class="macro-label">{label}</p>
                    <p class="macro-value">{value:.0f}g <span>/ {goal:.0f}g</span></p>
                </div>
                <span class="macro-percent">{percent}%</span>
            </div>
            <div class="macro-track">
                <div class="macro-fill" style="width:{percent}%; background:{color};"></div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_summary_card(summary: dict, title: str, subtitle: str) -> None:
    calorie_goal = calorie_target_from_profile() if st.session_state.profile_ready else CALORIE_GOAL
    progress = 0 if calorie_goal <= 0 else min(int((summary["calories"] / calorie_goal) * 100), 100)
    st.markdown(
        f"""
        <div class="hero-card screen-shell">
            <div class="hero-copy">
                <div class="pill">{title}</div>
                <h2>{summary["calories"]:.0f}</h2>
                <p>{subtitle}</p>
                <div class="hero-meter">
                    <div class="hero-meter-fill" style="width:{progress}%;"></div>
                </div>
                <div class="hero-foot">
                    <span>{progress}% of daily goal</span>
                    <span>{calorie_goal:.0f} kcal target</span>
                </div>
            </div>
            <div class="hero-ring" style="--progress:{progress};">
                <div class="hero-ring-inner">
                    <strong>{progress}%</strong>
                    <span>Goal</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def nutrition_donut(summary: dict):
    fig, ax = plt.subplots(figsize=(3.6, 3.6), facecolor="none")
    values = [max(summary["protein"], 0.01), max(summary["carbs"], 0.01), max(summary["fat"], 0.01)]
    colors = ["#4CAF50", "#88C057", "#F5B544"]
    labels = ["Protein", "Carbs", "Fats"]
    wedges, _ = ax.pie(
        values,
        colors=colors,
        startangle=90,
        wedgeprops=dict(width=0.34, edgecolor="#F8FBF5", linewidth=3),
    )
    ax.text(0, 0.02, f"{summary['calories']:.0f}", ha="center", va="center", fontsize=18, fontweight="bold", color="#17361d")
    ax.text(0, -0.16, "kcal", ha="center", va="center", fontsize=10, color="#6B7B69")
    patches = [mpatches.Patch(color=color, label=label) for color, label in zip(colors, labels)]
    ax.legend(handles=patches, loc="lower center", bbox_to_anchor=(0.5, -0.12), ncol=3, frameon=False, fontsize=9)
    ax.set(aspect="equal")
    fig.patch.set_alpha(0)
    return fig


def weekly_chart():
    labels, values = weekly_calorie_series()
    fig, ax = plt.subplots(figsize=(5.4, 2.8), facecolor="none")
    ax.bar(labels, values, color=["#A9D7A4", "#A9D7A4", "#A9D7A4", "#A9D7A4", "#8ACF7D", "#67C35C", "#4CAF50"], width=0.55)
    ax.plot(labels, values, color="#2E7D32", linewidth=2.2)
    ax.scatter(labels, values, color="#2E7D32", s=32, zorder=3)
    ax.spines[["top", "right", "left", "bottom"]].set_visible(False)
    ax.tick_params(axis="x", colors="#73816F", labelsize=9, length=0)
    ax.tick_params(axis="y", left=False, labelleft=False)
    ax.set_facecolor("none")
    fig.patch.set_alpha(0)
    return fig


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        :root {{
            --bg: #f5f9f2;
            --bg-strong: #eef6ea;
            --surface: rgba(255,255,255,0.92);
            --surface-muted: rgba(255,255,255,0.72);
            --ink: #18241d;
            --ink-soft: #6b7b69;
            --line: rgba(72, 116, 69, 0.08);
            --shadow: 0 18px 55px rgba(46, 125, 50, 0.08);
            --shadow-soft: 0 10px 28px rgba(46, 125, 50, 0.08);
            --green: #4CAF50;
            --green-dark: #2E7D32;
            --green-pale: #dff1de;
            --amber: #f5b544;
        }}

        html, body, [class*="css"], [data-testid="stAppViewContainer"] {{
            font-family: 'Inter', sans-serif;
        }}

        .stApp {{
            background:
                radial-gradient(circle at top left, rgba(124, 199, 102, 0.18), transparent 28%),
                radial-gradient(circle at top right, rgba(76, 175, 80, 0.10), transparent 26%),
                linear-gradient(180deg, #f7fbf5 0%, #eff6eb 100%);
            color: var(--ink);
        }}

        .ambient-scene {{
            position: fixed;
            inset: 0;
            pointer-events: none;
            overflow: hidden;
            z-index: 0;
        }}

        .wave-layer {{
            position: absolute;
            left: -10%;
            width: 120%;
            border-radius: 45% 55% 0 0 / 18% 18% 0 0;
            opacity: 0.92;
        }}

        .wave-a {{
            bottom: -20px;
            height: 240px;
            background: linear-gradient(90deg, rgba(209, 238, 202, 0.70), rgba(108, 191, 96, 0.30), rgba(209, 238, 202, 0.74));
            animation: waveFloatA 24s ease-in-out infinite;
            filter: blur(1px);
        }}

        .wave-b {{
            bottom: 52px;
            height: 210px;
            background: linear-gradient(90deg, rgba(170, 223, 161, 0.32), rgba(76, 175, 80, 0.28), rgba(170, 223, 161, 0.34));
            animation: waveFloatB 18s ease-in-out infinite;
            clip-path: polygon(0 75%, 10% 61%, 22% 80%, 35% 63%, 49% 82%, 63% 60%, 78% 79%, 90% 62%, 100% 78%, 100% 100%, 0 100%);
        }}

        .wave-c {{
            bottom: 118px;
            height: 180px;
            background: linear-gradient(90deg, rgba(214, 244, 210, 0.22), rgba(84, 181, 79, 0.18), rgba(214, 244, 210, 0.24));
            animation: waveFloatC 30s ease-in-out infinite;
            clip-path: polygon(0 80%, 14% 66%, 30% 85%, 46% 70%, 60% 84%, 74% 68%, 88% 82%, 100% 70%, 100% 100%, 0 100%);
        }}

        .floating-leaf, .floating-petal {{
            position: absolute;
            top: -12%;
            opacity: 0.75;
            animation-timing-function: linear;
            animation-iteration-count: infinite;
        }}

        .floating-leaf {{
            width: 22px;
            height: 44px;
            background: linear-gradient(180deg, rgba(118, 205, 102, 0.85), rgba(46, 125, 50, 0.88));
            border-radius: 100% 0 100% 0;
            transform: rotate(18deg);
            box-shadow: inset -2px -2px 0 rgba(255,255,255,0.15);
        }}

        .floating-petal {{
            width: 18px;
            height: 18px;
            background: radial-gradient(circle at 30% 30%, rgba(232, 248, 229, 0.95), rgba(129, 206, 118, 0.78));
            border-radius: 55% 45% 65% 35%;
            filter: blur(0.2px);
        }}

        .stApp::before,
        .stApp::after {{
            content: "";
            position: fixed;
            left: -12%;
            right: -12%;
            height: 320px;
            z-index: 0;
            pointer-events: none;
            opacity: 0.62;
        }}

        .stApp::before {{
            bottom: 128px;
            background: linear-gradient(90deg, rgba(193, 238, 184, 0.16), rgba(76, 175, 80, 0.22), rgba(46, 125, 50, 0.18), rgba(193, 238, 184, 0.16));
            clip-path: polygon(0 68%, 10% 61%, 20% 72%, 33% 58%, 45% 70%, 56% 55%, 67% 69%, 80% 60%, 91% 72%, 100% 63%, 100% 100%, 0 100%);
            filter: blur(1px);
            animation: waveDrift 18s linear infinite;
        }}

        .stApp::after {{
            bottom: 66px;
            background: linear-gradient(90deg, rgba(228, 246, 224, 0.52), rgba(138, 207, 125, 0.28), rgba(76, 175, 80, 0.2), rgba(228, 246, 224, 0.42));
            clip-path: polygon(0 76%, 12% 63%, 24% 80%, 37% 65%, 50% 79%, 63% 61%, 76% 76%, 88% 62%, 100% 79%, 100% 100%, 0 100%);
            filter: blur(3px);
            animation: waveDriftReverse 24s linear infinite;
        }}

        [data-testid="stAppViewContainer"]::before {{
            content: "";
            position: fixed;
            left: -8%;
            right: -8%;
            bottom: 24px;
            height: 250px;
            z-index: 0;
            pointer-events: none;
            background: linear-gradient(90deg, rgba(244, 251, 241, 0.70), rgba(114, 193, 97, 0.14), rgba(244, 251, 241, 0.7));
            clip-path: polygon(0 82%, 14% 66%, 28% 84%, 44% 70%, 57% 86%, 72% 67%, 86% 81%, 100% 68%, 100% 100%, 0 100%);
            animation: waveDrift 28s linear infinite;
        }}

        @keyframes waveDrift {{
            0% {{ transform: translateX(0); }}
            50% {{ transform: translateX(4%); }}
            100% {{ transform: translateX(0); }}
        }}

        @keyframes waveDriftReverse {{
            0% {{ transform: translateX(0); }}
            50% {{ transform: translateX(-4%); }}
            100% {{ transform: translateX(0); }}
        }}

        @keyframes waveFloatA {{
            0% {{ transform: translateX(0) translateY(0); }}
            50% {{ transform: translateX(5%) translateY(-8px); }}
            100% {{ transform: translateX(0) translateY(0); }}
        }}

        @keyframes waveFloatB {{
            0% {{ transform: translateX(0) translateY(0); }}
            50% {{ transform: translateX(-4%) translateY(10px); }}
            100% {{ transform: translateX(0) translateY(0); }}
        }}

        @keyframes waveFloatC {{
            0% {{ transform: translateX(0) translateY(0); }}
            50% {{ transform: translateX(3%) translateY(-12px); }}
            100% {{ transform: translateX(0) translateY(0); }}
        }}

        @keyframes leafFall {{
            0% {{ transform: translate3d(0, -12vh, 0) rotate(0deg); opacity: 0; }}
            10% {{ opacity: 0.75; }}
            100% {{ transform: translate3d(36px, 118vh, 0) rotate(320deg); opacity: 0; }}
        }}

        @keyframes petalFall {{
            0% {{ transform: translate3d(0, -12vh, 0) scale(0.9); opacity: 0; }}
            12% {{ opacity: 0.65; }}
            100% {{ transform: translate3d(-30px, 118vh, 0) scale(1.1) rotate(260deg); opacity: 0; }}
        }}

        @keyframes screenIn {{
            from {{ opacity: 0; transform: translateY(16px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        .block-container {{
            max-width: 1280px;
            padding-top: 0.6rem;
            padding-bottom: 7rem;
            position: relative;
            z-index: 1;
        }}

        [data-testid="stSidebar"] {{
            display: none;
        }}

        header[data-testid="stHeader"] {{
            background: transparent;
            position: relative;
            z-index: 60;
            pointer-events: auto;
        }}

        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"] {{
            position: relative;
            z-index: 61;
            pointer-events: auto;
        }}

        .screen-shell {{
            animation: screenIn 0.45s ease;
        }}

        .page-shell {{
            width: 100%;
        }}

        .content-panel {{
            width: min(100%, 1220px);
            margin: 0 auto;
        }}

        .navbar-shell {{
            background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(248,251,246,0.94));
            border: 1px solid rgba(83,118,80,0.10);
            border-radius: 22px;
            box-shadow: 0 4px 14px rgba(19, 39, 23, 0.05);
            padding: 0.95rem 1.35rem;
            margin-bottom: 1.2rem;
            backdrop-filter: blur(16px);
            position: relative;
            z-index: 20;
            pointer-events: auto;
        }}

        .navbar-shell [data-testid="stHorizontalBlock"] {{
            align-items: center;
        }}

        .nav-brand-wrap {{
            display: flex;
            align-items: center;
            gap: 0.65rem;
        }}

        .brand-link {{
            display: inline-flex;
            align-items: center;
            gap: 0.7rem;
            text-decoration: none;
            cursor: pointer;
            transition: opacity 160ms ease, transform 160ms ease;
        }}

        .brand-link:hover {{
            opacity: 0.8;
            transform: translateY(-1px);
        }}

        .brand-link:focus {{
            outline: none;
            box-shadow: 0 0 0 3px rgba(76,175,80,0.14);
            border-radius: 12px;
        }}

        .nav-brand-thumb {{
            width: 38px;
            height: 38px;
            border-radius: 10px;
            box-shadow: 0 8px 18px rgba(46, 125, 50, 0.10);
            object-fit: contain;
        }}

        .brand-text {{
            font-size: 1.12rem;
            font-weight: 800;
            color: var(--ink);
            white-space: nowrap;
            line-height: 1;
        }}

        .desktop-nav {{
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 0.85rem;
            flex-wrap: nowrap;
            overflow-x: auto;
            scrollbar-width: none;
            position: relative;
            z-index: 21;
            pointer-events: auto;
        }}

        .desktop-nav::-webkit-scrollbar {{
            display: none;
        }}

        .nav-button .stButton > button {{
            min-height: 48px !important;
            min-width: 108px !important;
            padding: 0.75rem 1.12rem !important;
            white-space: nowrap !important;
            flex-shrink: 0 !important;
            font-size: 1rem !important;
            font-weight: 700 !important;
            background: rgba(255,255,255,0.94) !important;
            color: var(--ink) !important;
            box-shadow: none !important;
            border: 1px solid rgba(83,118,80,0.12) !important;
            cursor: pointer !important;
            transition: background 160ms ease, border-color 160ms ease, transform 160ms ease !important;
            pointer-events: auto !important;
        }}

        .nav-button .stButton > button:hover {{
            background: rgba(76,175,80,0.08) !important;
            border-color: rgba(76,175,80,0.22) !important;
            transform: translateY(-1px);
        }}

        .nav-button .stButton > button:focus {{
            outline: none !important;
            box-shadow: 0 0 0 3px rgba(76,175,80,0.14) !important;
        }}

        .mobile-nav {{
            display: none !important;
            justify-content: flex-end;
            align-items: center;
            width: 100%;
            position: relative;
            z-index: 21;
            pointer-events: auto;
        }}

        .hamburger-button .stButton > button {{
            min-height: 38px !important;
            min-width: 38px !important;
            padding: 0.35rem 0.55rem !important;
            background: rgba(255,255,255,0.94) !important;
            color: var(--ink) !important;
            border: 1px solid rgba(83,118,80,0.12) !important;
            box-shadow: none !important;
            font-size: 1.05rem !important;
            font-weight: 800 !important;
            pointer-events: auto !important;
        }}

        .mobile-menu-panel {{
            background: rgba(255,255,255,0.98);
            border: 1px solid rgba(83,118,80,0.10);
            border-radius: 18px;
            box-shadow: var(--shadow-soft);
            padding: 0.65rem;
            margin-top: 0.55rem;
            position: relative;
            z-index: 22;
            pointer-events: auto;
        }}

        .mobile-menu-item .stButton > button {{
            min-height: 42px !important;
            width: 100% !important;
            white-space: nowrap !important;
            background: rgba(255,255,255,0.95) !important;
            color: var(--ink) !important;
            border: 1px solid rgba(83,118,80,0.10) !important;
            box-shadow: none !important;
            font-size: 0.92rem !important;
            font-weight: 700 !important;
            pointer-events: auto !important;
        }}

        .home-hero {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            padding: 1.8rem;
            background: linear-gradient(135deg, rgba(255,255,255,0.95), rgba(242, 249, 239, 0.94));
            border: 1px solid rgba(83,118,80,0.10);
            border-radius: 28px;
            box-shadow: var(--shadow);
        }}

        .home-hero-copy h2 {{
            margin: 0;
            font-size: 2.35rem;
            color: var(--ink);
        }}

        .home-hero-copy p {{
            margin: 0.45rem 0 0;
            color: var(--ink-soft);
            max-width: 620px;
            line-height: 1.7;
            font-size: 1.02rem;
        }}

        .action-card {{
            background: linear-gradient(135deg, #4CAF50 0%, #2E7D32 100%);
            border-radius: 24px;
            padding: 1.45rem;
            color: white;
            box-shadow: 0 18px 36px rgba(46, 125, 50, 0.18);
        }}

        .action-card h3 {{
            margin: 0;
            font-size: 1.15rem;
        }}

        .action-card p {{
            margin: 0.45rem 0 0.9rem;
            color: rgba(255,255,255,0.82);
            line-height: 1.5;
        }}

        .action-card .stButton > button {{
            background: white !important;
            color: var(--green-dark) !important;
        }}

        .preview-shell {{
            max-width: 100%;
            margin: 0;
            padding: 0.7rem;
            background: linear-gradient(180deg, rgba(255,255,255,0.94), rgba(244,250,241,0.92));
            border: 1px solid rgba(83,118,80,0.10);
            border-radius: 22px;
            box-shadow: var(--shadow-soft);
        }}

        .preview-frame {{
            height: 220px;
            max-height: 220px;
            border-radius: 18px;
            overflow: hidden;
            background: #f4f8f1;
            border: 1px solid rgba(83,118,80,0.08);
            display: flex;
            align-items: flex-start;
            justify-content: center;
        }}

        .preview-label {{
            margin: 0 0 0.65rem;
            color: var(--ink-soft);
            font-size: 0.84rem;
            font-weight: 700;
            text-align: center;
        }}

        .preview-frame img {{
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }}

        .upload-preview-group {{
            background: linear-gradient(180deg, rgba(255,255,255,0.95), rgba(245,250,242,0.94));
            border: 1px solid rgba(83,118,80,0.10);
            border-radius: 24px;
            box-shadow: var(--shadow-soft);
            padding: 1rem;
            margin-bottom: 0.9rem;
        }}

        .upload-pane-title {{
            margin: 0 0 0.45rem;
            color: var(--ink-soft);
            font-size: 0.82rem;
            font-weight: 700;
            letter-spacing: 0.02em;
        }}

        .dashboard-grid {{
            display: grid;
            grid-template-columns: minmax(0, 1.45fr) minmax(360px, 0.95fr);
            gap: 1.25rem;
            align-items: start;
        }}

        .stack-gap {{
            display: grid;
            gap: 1rem;
        }}

        .glass-card, .hero-card, .nav-shell, .insight-card, .meal-card, .calendar-card, .profile-card {{
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 24px;
            box-shadow: var(--shadow);
            backdrop-filter: blur(20px);
        }}

        .hero-card {{
            padding: 1.35rem;
            background: linear-gradient(135deg, #4CAF50 0%, #2E7D32 100%);
            color: white;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 1rem;
            position: relative;
            overflow: hidden;
        }}

        .hero-card::after {{
            content: "";
            position: absolute;
            inset: auto -30px -45px auto;
            width: 180px;
            height: 180px;
            border-radius: 999px;
            background: radial-gradient(circle, rgba(255,255,255,0.18), transparent 65%);
        }}

        .pill {{
            display: inline-flex;
            padding: 0.38rem 0.8rem;
            border-radius: 999px;
            background: rgba(255,255,255,0.16);
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.04em;
            margin-bottom: 0.8rem;
        }}

        .hero-copy h2 {{
            margin: 0;
            font-size: 2.4rem;
            line-height: 1;
        }}

        .hero-copy p {{
            margin: 0.45rem 0 1rem;
            color: rgba(255,255,255,0.82);
            font-size: 0.95rem;
        }}

        .hero-meter {{
            height: 10px;
            background: rgba(255,255,255,0.22);
            border-radius: 999px;
            overflow: hidden;
        }}

        .hero-meter-fill {{
            height: 100%;
            border-radius: inherit;
            background: linear-gradient(90deg, #dff6dc, #ffffff);
            transition: width 700ms ease;
        }}

        .hero-foot {{
            margin-top: 0.7rem;
            display: flex;
            justify-content: space-between;
            font-size: 0.78rem;
            color: rgba(255,255,255,0.8);
            gap: 1rem;
        }}

        .hero-ring {{
            width: 120px;
            height: 120px;
            min-width: 120px;
            border-radius: 50%;
            background: conic-gradient(#ffffff calc(var(--progress) * 1%), rgba(255,255,255,0.24) 0);
            display: grid;
            place-items: center;
            position: relative;
            box-shadow: inset 0 0 0 10px rgba(255,255,255,0.08);
        }}

        .hero-ring-inner {{
            width: 84px;
            height: 84px;
            border-radius: 50%;
            background: rgba(37, 92, 41, 0.96);
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.12);
        }}

        .hero-ring-inner strong {{
            font-size: 1.15rem;
        }}

        .hero-ring-inner span {{
            font-size: 0.74rem;
            color: rgba(255,255,255,0.72);
        }}

        .top-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 0.9rem;
        }}

        .greeting h1 {{
            margin: 0;
            font-size: 1.7rem;
            line-height: 1.1;
        }}

        .greeting p {{
            margin: 0.25rem 0 0;
            color: var(--ink-soft);
            font-size: 0.95rem;
        }}

        .avatar-chip {{
            width: 48px;
            height: 48px;
            border-radius: 18px;
            display: grid;
            place-items: center;
            background: linear-gradient(135deg, #dff1de, #f8fff6);
            border: 1px solid rgba(76,175,80,0.12);
            color: var(--green-dark);
            font-weight: 800;
            box-shadow: var(--shadow-soft);
        }}

        .section-card {{
            background: var(--surface);
            border: 1px solid var(--line);
            border-radius: 22px;
            padding: 1.35rem;
            box-shadow: var(--shadow-soft);
            margin-bottom: 1rem;
            transition: transform 200ms ease, box-shadow 200ms ease;
        }}

        .section-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 18px 40px rgba(46, 125, 50, 0.10);
        }}

        .section-head {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 0.9rem;
        }}

        .section-head h3 {{
            margin: 0;
            font-size: 1rem;
        }}

        .section-head span {{
            font-size: 0.85rem;
            color: var(--green-dark);
            font-weight: 700;
        }}

        .explain-card {{
            background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(240,248,236,0.94));
            border: 1px solid rgba(83,118,80,0.10);
            border-radius: 24px;
            padding: 1.2rem;
            box-shadow: var(--shadow-soft);
        }}

        .explain-card ol {{
            margin: 0.7rem 0 0;
            padding-left: 1.1rem;
            color: var(--ink-soft);
        }}

        .explain-card li {{
            margin-bottom: 0.55rem;
            line-height: 1.5;
        }}

        .search-shell {{
            padding: 0.2rem 0 0.6rem;
        }}

        [data-testid="stTextInput"] input,
        [data-testid="stNumberInput"] input,
        textarea {{
            background: rgba(255,255,255,0.92) !important;
            border: 1px solid rgba(83, 118, 80, 0.12) !important;
            color: var(--ink) !important;
            border-radius: 18px !important;
            min-height: 56px !important;
            padding: 0.95rem 1.05rem !important;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.7);
            transition: box-shadow 200ms ease, transform 200ms ease !important;
            font-size: 0.98rem !important;
        }}

        [data-testid="stTextInput"] input:focus,
        [data-testid="stNumberInput"] input:focus {{
            border-color: rgba(76, 175, 80, 0.32) !important;
            box-shadow: 0 0 0 4px rgba(76, 175, 80, 0.09) !important;
        }}

        [data-testid="stFileUploader"] > div {{
            background: linear-gradient(180deg, #fcfffb, #f3f9f1) !important;
            border: 2px dashed rgba(76, 175, 80, 0.24) !important;
            border-radius: 24px !important;
            padding: 0.35rem !important;
            transition: transform 220ms ease, box-shadow 220ms ease, border-color 220ms ease !important;
        }}

        [data-testid="stFileUploader"] > div:hover {{
            transform: scale(1.01);
            border-color: rgba(76, 175, 80, 0.46) !important;
            box-shadow: 0 20px 45px rgba(76, 175, 80, 0.12);
        }}

        [data-testid="stFileUploaderDropzone"] {{
            min-height: 170px !important;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        .stButton > button {{
            width: 100%;
            min-height: 54px;
            border-radius: 18px !important;
            border: none !important;
            background: linear-gradient(135deg, #4CAF50 0%, #2E7D32 100%) !important;
            color: white !important;
            font-weight: 700 !important;
            font-size: 0.98rem !important;
            box-shadow: 0 14px 28px rgba(46, 125, 50, 0.18) !important;
            transition: transform 180ms ease, box-shadow 180ms ease !important;
        }}

        .stButton > button:hover {{
            transform: translateY(-2px) scale(1.01);
            box-shadow: 0 18px 34px rgba(46, 125, 50, 0.22) !important;
        }}

        .stButton > button:active {{
            transform: scale(0.98);
        }}

        .ghost-button .stButton > button,
        .nav-shell .stButton > button,
        .chip-row .stButton > button {{
            background: white !important;
            color: var(--ink) !important;
            box-shadow: none !important;
            border: 1px solid rgba(83,118,80,0.10) !important;
        }}

        .nav-shell {{
            position: fixed;
            left: 50%;
            transform: translateX(-50%);
            bottom: 16px;
            width: min(470px, calc(100vw - 22px));
            padding: 0.7rem;
            z-index: 5;
        }}

        .nav-label {{
            text-align: center;
            font-size: 0.7rem;
            color: var(--ink-soft);
            margin-top: 0.25rem;
            font-weight: 600;
        }}

        .nav-active .nav-label {{
            color: var(--green-dark);
        }}

        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.85rem;
        }}

        .kpi-card {{
            background: linear-gradient(180deg, #ffffff, #f7fbf5);
            border: 1px solid rgba(83,118,80,0.08);
            border-radius: 20px;
            padding: 0.95rem;
            box-shadow: var(--shadow-soft);
        }}

        .kpi-card strong {{
            display: block;
            font-size: 1.22rem;
            margin-top: 0.25rem;
            color: var(--ink);
        }}

        .kpi-card span {{
            color: var(--ink-soft);
            font-size: 0.82rem;
        }}

        .macro-row {{
            margin-bottom: 0.9rem;
        }}

        .macro-row-head {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 0.45rem;
        }}

        .macro-label {{
            margin: 0;
            font-size: 0.83rem;
            color: var(--ink-soft);
            font-weight: 700;
        }}

        .macro-value {{
            margin: 0.1rem 0 0;
            font-size: 1.02rem;
            font-weight: 700;
            color: var(--ink);
        }}

        .macro-value span {{
            color: var(--ink-soft);
            font-weight: 600;
            font-size: 0.88rem;
        }}

        .macro-percent {{
            font-size: 0.82rem;
            font-weight: 700;
            color: var(--green-dark);
        }}

        .macro-track {{
            height: 10px;
            background: #edf4ea;
            border-radius: 999px;
            overflow: hidden;
        }}

        .macro-fill {{
            height: 100%;
            border-radius: inherit;
            transition: width 700ms ease;
        }}

        .food-strip {{
            display: flex;
            gap: 0.85rem;
            overflow-x: auto;
            padding-bottom: 0.2rem;
            scrollbar-width: none;
        }}

        .food-strip::-webkit-scrollbar {{
            display: none;
        }}

        .food-card {{
            min-width: 148px;
            background: linear-gradient(180deg, #ffffff, #f8fcf6);
            border: 1px solid rgba(83,118,80,0.08);
            border-radius: 22px;
            padding: 0.95rem;
            box-shadow: var(--shadow-soft);
        }}

        .food-thumb {{
            width: 52px;
            height: 52px;
            border-radius: 18px;
            display: grid;
            place-items: center;
            background: linear-gradient(135deg, #dff1de, #b7deb4);
            color: var(--green-dark);
            font-weight: 800;
            margin-bottom: 0.75rem;
        }}

        .food-card h4 {{
            margin: 0;
            font-size: 0.95rem;
            line-height: 1.2;
        }}

        .food-card p {{
            margin: 0.3rem 0 0;
            color: var(--ink-soft);
            font-size: 0.8rem;
        }}

        .food-card strong {{
            display: block;
            margin-top: 0.5rem;
            color: var(--green-dark);
        }}

        .result-food-list {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 0.8rem;
        }}

        .result-food-item {{
            background: linear-gradient(180deg, #ffffff, #f6fbf4);
            border: 1px solid rgba(83,118,80,0.08);
            border-radius: 20px;
            padding: 1rem;
            box-shadow: var(--shadow-soft);
        }}

        .result-food-item h4 {{
            margin: 0;
            font-size: 0.98rem;
        }}

        .result-food-item p {{
            margin: 0.35rem 0 0;
            color: var(--ink-soft);
            font-size: 0.82rem;
        }}

        .detected-summary {{
            margin: 0.35rem 0 0.95rem;
            color: var(--ink-soft);
            font-size: 0.9rem;
            font-weight: 600;
        }}

        .nutrient-grid {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.75rem;
            margin-top: 0.35rem;
        }}

        .nutrient-chip {{
            background: linear-gradient(180deg, #ffffff, #f7fbf5);
            border: 1px solid rgba(83,118,80,0.08);
            border-radius: 18px;
            padding: 0.8rem 0.9rem;
        }}

        .nutrient-chip strong {{
            display: block;
            color: var(--ink);
            font-size: 0.95rem;
            margin-top: 0.2rem;
        }}

        .nutrient-chip span {{
            color: var(--ink-soft);
            font-size: 0.78rem;
            font-weight: 700;
        }}

        .nutrient-chip.calories {{
            border-color: rgba(245, 181, 68, 0.28);
            background: linear-gradient(180deg, rgba(255,247,226,0.95), #fffdf8);
        }}

        .nutrient-chip.protein {{
            border-color: rgba(76, 175, 80, 0.22);
            background: linear-gradient(180deg, rgba(236,248,235,0.96), #fbfefb);
        }}

        .nutrient-chip.carbs {{
            border-color: rgba(136, 192, 87, 0.24);
            background: linear-gradient(180deg, rgba(243,250,231,0.96), #fcfef9);
        }}

        .nutrient-chip.fats {{
            border-color: rgba(255, 209, 94, 0.28);
            background: linear-gradient(180deg, rgba(255,249,228,0.96), #fffef9);
        }}

        [data-testid="stExpander"] {{
            background: rgba(255,255,255,0.84) !important;
            border: 1px solid rgba(83,118,80,0.10) !important;
            border-radius: 18px !important;
            margin-bottom: 0.8rem !important;
            box-shadow: var(--shadow-soft);
            overflow: hidden !important;
        }}

        [data-testid="stExpander"] summary {{
            padding: 0.9rem 1rem !important;
            font-weight: 700 !important;
            color: var(--ink) !important;
        }}

        [data-testid="stExpander"] summary:hover {{
            color: var(--green-dark) !important;
        }}

        [data-testid="stExpanderDetails"] {{
            padding: 0 1rem 1rem !important;
        }}

        .calendar-card {{
            padding: 1rem;
            margin-bottom: 1rem;
        }}

        .calendar-grid {{
            display: grid;
            grid-template-columns: repeat(7, minmax(0, 1fr));
            gap: 0.48rem;
        }}

        .calendar-weekday {{
            text-align: center;
            font-size: 0.74rem;
            color: var(--ink-soft);
            font-weight: 700;
            padding-bottom: 0.35rem;
        }}

        .calendar-day {{
            min-height: 52px;
            border-radius: 18px;
            background: #f7fbf5;
            border: 1px solid rgba(83,118,80,0.06);
            display: flex;
            align-items: center;
            justify-content: center;
            flex-direction: column;
            color: var(--ink);
            font-weight: 700;
            position: relative;
        }}

        .calendar-day.empty {{
            background: transparent;
            border-color: transparent;
        }}

        .calendar-day.selected {{
            background: linear-gradient(135deg, #4CAF50, #2E7D32);
            color: white;
            box-shadow: 0 16px 30px rgba(46, 125, 50, 0.18);
        }}

        .calendar-day.has-entry:not(.selected) {{
            background: linear-gradient(180deg, #ffffff, #eff8ec);
        }}

        .calendar-dot {{
            width: 6px;
            height: 6px;
            border-radius: 999px;
            background: var(--amber);
            margin-top: 0.25rem;
        }}

        .calendar-day.selected .calendar-dot {{
            background: white;
        }}

        .meal-card {{
            padding: 1rem;
            margin-bottom: 0.8rem;
            transition: transform 180ms ease, box-shadow 180ms ease;
        }}

        .meal-card:hover {{
            transform: translateY(-2px) scale(1.01);
            box-shadow: 0 20px 36px rgba(46, 125, 50, 0.12);
        }}

        .meal-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.9rem;
        }}

        .meal-meta h4 {{
            margin: 0;
            font-size: 0.95rem;
        }}

        .meal-meta p {{
            margin: 0.25rem 0 0;
            color: var(--ink-soft);
            font-size: 0.82rem;
        }}

        .meal-kcal {{
            color: var(--green-dark);
            font-weight: 800;
            white-space: nowrap;
        }}

        .profile-hero {{
            text-align: center;
            padding: 1.45rem 1.2rem 1.2rem;
        }}

        .profile-avatar-shell {{
            position: relative;
            width: 118px;
            margin: 0 auto 1rem;
        }}

        .profile-avatar-ring {{
            width: 118px;
            height: 118px;
            border-radius: 999px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 20px 34px rgba(46, 125, 50, 0.12), inset 0 1px 0 rgba(255,255,255,0.7);
            border: 1px solid rgba(83,118,80,0.10);
            overflow: visible;
        }}

        .profile-avatar-bust {{
            font-size: 4rem;
            line-height: 1;
            transform: translateY(8px);
            filter: drop-shadow(0 8px 10px rgba(20, 42, 22, 0.10));
        }}

        .profile-avatar-badge {{
            position: absolute;
            right: 4px;
            bottom: 8px;
            width: 34px;
            height: 34px;
            border-radius: 999px;
            background: linear-gradient(135deg, #4CAF50, #2E7D32);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.9rem;
            font-weight: 800;
            border: 3px solid white;
            box-shadow: 0 8px 18px rgba(46,125,50,0.18);
        }}

        .profile-name {{
            margin: 0;
            font-size: 1.55rem;
            font-weight: 800;
            color: var(--ink);
        }}

        .profile-tagline {{
            margin: 0.35rem auto 0;
            max-width: 360px;
            color: var(--ink-soft);
            font-size: 0.95rem;
            line-height: 1.5;
        }}

        .avatar-change-note {{
            margin-top: 0.65rem;
            color: var(--ink-soft);
            font-size: 0.8rem;
            font-weight: 600;
        }}

        .login-shell {{
            padding-top: 1rem;
        }}

        .login-hero {{
            background: linear-gradient(180deg, rgba(255,255,255,0.92), rgba(255,255,255,0.82));
            border: 1px solid rgba(83,118,80,0.08);
            border-radius: 32px;
            padding: 1.5rem;
            box-shadow: var(--shadow);
            position: relative;
            overflow: hidden;
        }}

        .login-hero::before {{
            content: "";
            position: absolute;
            inset: auto -30px -50px auto;
            width: 180px;
            height: 180px;
            background: radial-gradient(circle, rgba(76, 175, 80, 0.14), transparent 68%);
            border-radius: 50%;
        }}

        .login-copy h1 {{
            margin: 0.9rem 0 0.6rem;
            font-size: 2.2rem;
            line-height: 1.05;
        }}

        .login-copy h1 span {{
            color: var(--green);
        }}

        .login-copy p {{
            margin: 0;
            color: var(--ink-soft);
            font-size: 0.98rem;
            line-height: 1.55;
            max-width: 320px;
        }}

        .login-note {{
            margin-top: 1rem;
            padding: 0.85rem 1rem;
            background: rgba(223, 241, 222, 0.7);
            border-radius: 18px;
            color: #466645;
            font-size: 0.85rem;
            border: 1px solid rgba(76,175,80,0.10);
        }}

        .auth-shell {{
            width: min(100%, 980px);
            margin: 0 auto;
            display: grid;
            grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
            gap: 1.1rem;
            align-items: stretch;
        }}

        .auth-hero-panel, .auth-form-panel, .onboarding-panel, .profile-identity-card, .profile-detail-card {{
            background: linear-gradient(180deg, rgba(255,255,255,0.94), rgba(248,251,246,0.9));
            border: 1px solid rgba(83,118,80,0.10);
            border-radius: 28px;
            box-shadow: var(--shadow);
            backdrop-filter: blur(18px);
        }}

        .auth-hero-panel {{
            padding: 1.6rem;
            position: relative;
            overflow: hidden;
        }}

        .auth-hero-panel::before, .onboarding-panel::before, .profile-identity-card::before {{
            content: "";
            position: absolute;
            inset: auto -38px -56px auto;
            width: 210px;
            height: 210px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(76,175,80,0.14), transparent 68%);
            pointer-events: none;
        }}

        .auth-form-panel, .onboarding-panel {{
            padding: 1.55rem;
        }}

        .hero-avatar-stack {{
            display: flex;
            justify-content: center;
            gap: 0.5rem;
            margin-top: 1.4rem;
        }}

        .progress-dots {{
            display: flex;
            gap: 0.45rem;
            margin: 0.8rem 0 1.15rem;
        }}

        .progress-dot {{
            flex: 1;
            height: 10px;
            border-radius: 999px;
            background: rgba(76,175,80,0.12);
            overflow: hidden;
        }}

        .progress-dot.active {{
            background: linear-gradient(90deg, #89D57D, #4CAF50);
            box-shadow: 0 10px 18px rgba(76,175,80,0.16);
        }}

        .step-kicker {{
            margin: 0;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 800;
            color: var(--green-dark);
        }}

        .step-title {{
            margin: 0.45rem 0 0.35rem;
            font-size: 2rem;
            line-height: 1.05;
            color: var(--ink);
        }}

        .step-copy {{
            margin: 0 0 1rem;
            color: var(--ink-soft);
            line-height: 1.6;
            max-width: 460px;
        }}

        .premium-avatar {{
            text-align: center;
        }}

        .premium-avatar-orb {{
            position: relative;
            margin: 0 auto;
            border-radius: 999px;
            border: 1px solid rgba(83,118,80,0.10);
            box-shadow: 0 24px 42px rgba(46,125,50,0.12), inset 0 1px 0 rgba(255,255,255,0.7);
            overflow: visible;
        }}

        .premium-avatar-profile .premium-avatar-orb {{
            width: 116px;
            height: 116px;
        }}

        .premium-avatar-home .premium-avatar-orb {{
            width: 66px;
            height: 66px;
        }}

        .premium-avatar-chooser .premium-avatar-orb {{
            width: 92px;
            height: 92px;
        }}

        .premium-avatar-figure {{
            position: absolute;
            inset: -18px 0 auto;
            width: 100%;
            height: auto;
            filter: drop-shadow(0 16px 20px rgba(24,36,29,0.18));
            transition: transform 180ms ease;
        }}

        .premium-avatar:hover .premium-avatar-figure {{
            transform: translateY(-2px) scale(1.02);
        }}

        .premium-avatar.selected .premium-avatar-orb {{
            box-shadow: 0 0 0 4px rgba(76,175,80,0.14), 0 26px 44px rgba(46,125,50,0.16);
            border-color: rgba(76,175,80,0.38);
        }}

        .premium-avatar-name {{
            margin-top: 0.55rem;
            color: var(--ink);
            font-size: 0.84rem;
            font-weight: 700;
        }}

        .premium-avatar-edit {{
            position: absolute;
            right: -4px;
            bottom: 2px;
            padding: 0.28rem 0.45rem;
            border-radius: 999px;
            background: linear-gradient(135deg, #4CAF50, #2E7D32);
            color: white;
            font-size: 0.62rem;
            font-weight: 800;
            border: 2px solid white;
            box-shadow: 0 10px 18px rgba(46,125,50,0.18);
        }}

        .profile-shell {{
            width: min(100%, 480px);
            margin: 0 auto;
        }}

        .profile-identity-card {{
            position: relative;
            text-align: center;
            padding: 1.55rem 1.45rem 1.35rem;
            overflow: hidden;
        }}

        .profile-identity-card .premium-avatar {{
            margin-bottom: 0.75rem;
        }}

        .profile-identity-card .premium-avatar-name {{
            display: none;
        }}

        .identity-greeting {{
            margin: 0.15rem 0 0;
            font-size: 1.62rem;
            font-weight: 800;
            color: var(--ink);
        }}

        .identity-name {{
            margin: 0.4rem 0 0;
            font-size: 1rem;
            color: var(--ink-soft);
            font-weight: 700;
        }}

        .identity-tagline {{
            margin: 0.55rem auto 1rem;
            max-width: 320px;
            color: var(--ink-soft);
            line-height: 1.55;
        }}

        .identity-meta {{
            display: flex;
            justify-content: center;
            gap: 0.55rem;
            flex-wrap: wrap;
            margin-bottom: 1rem;
        }}

        .identity-pill {{
            padding: 0.45rem 0.75rem;
            border-radius: 999px;
            background: rgba(255,255,255,0.78);
            border: 1px solid rgba(83,118,80,0.08);
            color: var(--ink-soft);
            font-size: 0.8rem;
            font-weight: 700;
        }}

        .profile-stats-row {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.65rem;
            margin: 1rem 0 0.95rem;
        }}

        .profile-stat-pill {{
            padding: 0.85rem 0.7rem;
            border-radius: 18px;
            background: rgba(255,255,255,0.84);
            border: 1px solid rgba(83,118,80,0.08);
            box-shadow: var(--shadow-soft);
        }}

        .profile-stat-pill span {{
            display: block;
            font-size: 0.72rem;
            color: var(--ink-soft);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}

        .profile-stat-pill strong {{
            display: block;
            margin-top: 0.28rem;
            color: var(--ink);
            font-size: 1.12rem;
        }}

        .profile-action-row {{
            display: flex;
            gap: 0.7rem;
            justify-content: center;
            flex-wrap: wrap;
        }}

        .profile-detail-card {{
            padding: 1.1rem;
            margin-top: 1rem;
        }}

        .profile-popover-trigger {{
            max-width: 220px;
            margin: 0.35rem auto 0;
        }}

        .profile-popover-trigger .stButton > button {{
            min-height: 42px !important;
            background: rgba(255,255,255,0.94) !important;
            color: var(--ink) !important;
            border: 1px solid rgba(83,118,80,0.10) !important;
            box-shadow: none !important;
        }}

        .profile-panel-card {{
            width: 100%;
            margin: 0 auto 1rem;
            padding: 1.55rem 1.45rem;
            border-radius: 24px;
            background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(244,250,241,0.94));
            border: 1px solid rgba(83,118,80,0.10);
            box-shadow: var(--shadow);
            text-align: center;
        }}

        .profile-avatar-wrap {{
            position: relative;
            width: 116px;
            margin: 0 auto 0.9rem;
        }}

        .profile-edit-chip {{
            position: absolute;
            right: -2px;
            bottom: 4px;
            padding: 0.26rem 0.5rem;
            border-radius: 999px;
            background: linear-gradient(135deg, #4CAF50 0%, #2E7D32 100%);
            color: white;
            font-size: 0.68rem;
            font-weight: 800;
            border: 2px solid white;
            box-shadow: 0 8px 16px rgba(46,125,50,0.16);
        }}

        .profile-title {{
            margin: 0;
            font-size: 1.55rem;
            font-weight: 800;
            color: var(--ink);
        }}

        .profile-subtitle {{
            margin: 0.45rem auto 0.95rem;
            color: var(--ink-soft);
            line-height: 1.55;
            max-width: 320px;
            font-size: 0.92rem;
        }}

        .profile-stat-grid {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 0.7rem;
            margin: 1rem 0 0.95rem;
        }}

        .profile-stat-item {{
            padding: 0.85rem 0.7rem;
            border-radius: 18px;
            background: rgba(255,255,255,0.82);
            border: 1px solid rgba(83,118,80,0.08);
            box-shadow: var(--shadow-soft);
        }}

        .profile-stat-item span {{
            display: block;
            color: var(--ink-soft);
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }}

        .profile-stat-item strong {{
            display: block;
            margin-top: 0.24rem;
            font-size: 1.08rem;
            color: var(--ink);
        }}

        .profile-pill-row {{
            display: flex;
            justify-content: center;
            gap: 0.55rem;
            flex-wrap: wrap;
        }}

        .profile-pill {{
            padding: 0.45rem 0.78rem;
            border-radius: 999px;
            background: rgba(255,255,255,0.84);
            border: 1px solid rgba(83,118,80,0.08);
            color: var(--ink-soft);
            font-size: 0.8rem;
            font-weight: 700;
        }}

        .profile-section-card {{
            width: 100%;
            margin: 0 auto 1rem;
            padding: 1.15rem;
            border-radius: 22px;
            background: rgba(255,255,255,0.94);
            border: 1px solid rgba(83,118,80,0.08);
            box-shadow: var(--shadow-soft);
        }}

        .profile-dashboard {{
            display: grid;
            grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
            gap: 1.5rem;
            align-items: start;
            max-width: 1100px;
            margin: 0 auto;
        }}

        .profile-column-stack {{
            display: grid;
            gap: 1rem;
            align-content: start;
        }}

        .field-label {{
            margin: 0 0 0.38rem;
            color: var(--ink-soft);
            font-size: 0.82rem;
            font-weight: 700;
        }}

        .profile-grid {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 1rem;
        }}

        .subtle-note {{
            text-align: center;
            color: var(--ink-soft);
            font-size: 0.82rem;
            margin-top: 0.8rem;
        }}

        [data-testid="stRadio"] > div {{
            gap: 0.75rem;
        }}

        [data-testid="stRadio"] label {{
            background: white;
            padding: 0.6rem 0.9rem;
            border-radius: 16px;
            border: 1px solid rgba(83,118,80,0.08);
        }}

        [data-testid="stMetric"] {{
            background: linear-gradient(180deg, #ffffff, #f7fbf5) !important;
            border: 1px solid rgba(83,118,80,0.08) !important;
            border-radius: 18px !important;
            padding: 1rem !important;
            box-shadow: var(--shadow-soft);
        }}

        [data-testid="stMetricLabel"] p {{
            color: var(--ink-soft) !important;
            font-size: 0.78rem !important;
            font-weight: 700 !important;
        }}

        [data-testid="stMetricValue"] {{
            color: var(--ink) !important;
            font-size: 1.12rem !important;
            font-weight: 800 !important;
        }}

        .empty-panel {{
            text-align: center;
            padding: 2rem 1.4rem;
            background: linear-gradient(180deg, rgba(255,255,255,0.9), rgba(250,253,248,0.85));
            border: 1px dashed rgba(83,118,80,0.18);
            border-radius: 24px;
            color: var(--ink-soft);
        }}

        .empty-state-card {{
            text-align: center;
            padding: 2rem 1.4rem;
            background: linear-gradient(180deg, rgba(255,255,255,0.96), rgba(246,251,244,0.92));
            border: 1px dashed rgba(83,118,80,0.18);
            border-radius: 24px;
            color: var(--ink-soft);
        }}

        .empty-state-icon {{
            width: 64px;
            height: 64px;
            margin: 0 auto 0.9rem;
            border-radius: 20px;
            display: grid;
            place-items: center;
            background: linear-gradient(135deg, #eff7ea, #dcefd6);
            font-size: 1.8rem;
        }}

        .empty-state-card h4 {{
            margin: 0;
            color: var(--ink);
            font-size: 1rem;
        }}

        .empty-state-card p {{
            margin: 0.45rem 0 0;
            font-size: 0.85rem;
        }}

        .empty-state-badge {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 0.75rem;
            padding: 0.28rem 0.72rem;
            border-radius: 999px;
            background: rgba(76,175,80,0.10);
            color: var(--green-dark);
            font-size: 0.75rem;
            font-weight: 700;
        }}

        .small-muted {{
            font-size: 0.78rem;
            color: var(--ink-soft);
        }}

        hr {{
            margin: 0.6rem 0 1rem !important;
            border-color: rgba(83,118,80,0.08) !important;
        }}

        @media (max-width: 960px) {{
            .dashboard-grid {{
                grid-template-columns: 1fr;
            }}

            .content-panel {{
                width: 100%;
            }}

            .auth-shell {{
                grid-template-columns: 1fr;
            }}

            .profile-dashboard {{
                grid-template-columns: 1fr;
            }}
        }}

        @media (max-width: 768px) {{
            .desktop-nav {{
                display: none;
            }}

            .mobile-nav {{
                display: flex !important;
            }}
        }}

        @media (max-width: 640px) {{

            .hero-card {{
                flex-direction: column;
                align-items: flex-start;
            }}

            .home-hero {{
                flex-direction: column;
                align-items: flex-start;
            }}

            .hero-copy h2 {{
                font-size: 2rem;
            }}

            .kpi-grid {{
                grid-template-columns: 1fr;
            }}

            .profile-grid {{
                grid-template-columns: 1fr;
            }}

            .profile-stats-row {{
                grid-template-columns: 1fr;
            }}

            .profile-stat-grid {{
                grid-template-columns: 1fr;
            }}

            .nutrient-grid {{
                grid-template-columns: 1fr;
            }}

            .preview-frame {{
                height: 200px;
                max-height: 200px;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_background_scene() -> None:
    st.markdown(
        """
        <div class="ambient-scene" aria-hidden="true">
            <div class="wave-layer wave-a"></div>
            <div class="wave-layer wave-b"></div>
            <div class="wave-layer wave-c"></div>
            <span class="floating-leaf" style="left:6%; animation: leafFall 18s linear infinite; animation-delay:-2s;"></span>
            <span class="floating-leaf" style="left:18%; animation: leafFall 22s linear infinite; animation-delay:-11s;"></span>
            <span class="floating-leaf" style="left:36%; animation: leafFall 20s linear infinite; animation-delay:-7s;"></span>
            <span class="floating-leaf" style="left:57%; animation: leafFall 24s linear infinite; animation-delay:-14s;"></span>
            <span class="floating-leaf" style="left:78%; animation: leafFall 19s linear infinite; animation-delay:-5s;"></span>
            <span class="floating-petal" style="left:12%; animation: petalFall 17s linear infinite; animation-delay:-4s;"></span>
            <span class="floating-petal" style="left:28%; animation: petalFall 21s linear infinite; animation-delay:-10s;"></span>
            <span class="floating-petal" style="left:49%; animation: petalFall 16s linear infinite; animation-delay:-8s;"></span>
            <span class="floating-petal" style="left:68%; animation: petalFall 23s linear infinite; animation-delay:-13s;"></span>
            <span class="floating-petal" style="left:88%; animation: petalFall 19s linear infinite; animation-delay:-6s;"></span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_brand(show_routes: bool = True) -> None:
    st.markdown('<div class="navbar-shell screen-shell">', unsafe_allow_html=True)
    left, center, right = st.columns([1.35, 4.45, 0.45], vertical_alignment="center")
    with left:
        home_screen = "Home" if has_authenticated_user() or st.session_state.guest_mode else "Login"
        st.markdown(
            f"""
            <a class="brand-link" href="?screen={home_screen}">
                <img class="nav-brand-thumb" src="{ICON_URI}" alt="NutriSeeker logo" />
                <span class="brand-text">NutriSeeker</span>
            </a>
            """,
            unsafe_allow_html=True,
        )

    with center:
        if show_routes:
            st.markdown('<div class="desktop-nav">', unsafe_allow_html=True)
            nav_cols = st.columns([1.05, 1.0, 0.95, 1.1, 1.1, 1.0])
            for column, (screen, label) in zip(nav_cols, route_options()):
                with column:
                    st.markdown('<div class="nav-button">', unsafe_allow_html=True)
                    if st.button(label, key=f"route_{screen}", use_container_width=True):
                        navigate_to(screen)
                        st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    with right:
        if show_routes:
            st.markdown('<div class="mobile-nav"><div class="hamburger-button">', unsafe_allow_html=True)
            if st.button("☰", key="mobile_menu_toggle", use_container_width=True):
                st.session_state.mobile_menu_open = not st.session_state.get("mobile_menu_open", False)
                st.rerun()
            st.markdown('</div></div>', unsafe_allow_html=True)

    if show_routes and st.session_state.get("mobile_menu_open", False):
        st.markdown('<div class="mobile-menu-panel screen-shell">', unsafe_allow_html=True)
        menu_cols = st.columns(2)
        for idx, (screen, label) in enumerate(route_options()):
            with menu_cols[idx % 2]:
                st.markdown('<div class="mobile-menu-item">', unsafe_allow_html=True)
                if st.button(label, key=f"mobile_route_{screen}", use_container_width=True):
                    navigate_to(screen)
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


def render_avatar_selection(selected_avatar: str, *, key_prefix: str) -> None:
    columns = st.columns(4, gap="small")
    for index, spec in enumerate(AVATAR_SPECS):
        with columns[index % 4]:
            render_avatar_image(spec["id"], width=96)
            suffix = " • selected" if selected_avatar == spec["id"] else ""
            st.caption(f"{spec['name']}{suffix}")
            if st.button(
                "Selected" if selected_avatar == spec["id"] else "Choose",
                key=f"{key_prefix}_{spec['id']}",
                use_container_width=True,
            ):
                st.session_state.profile_avatar = spec["id"]
                st.rerun()


def render_login_screen() -> None:
    render_brand(show_routes=True)
    st.markdown('<div class="auth-shell screen-shell">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="auth-hero-panel">
            <div class="pill" style="background:rgba(76,175,80,0.10); color:#2E7D32;">Premium nutrition experience</div>
            <div class="login-copy">
                <h1>Track your <span>nutrition smartly</span></h1>
                <p>AI-powered insights for healthier daily eating, meal analysis, and progress tracking.</p>
            </div>
            <div class="login-note">Sign in to continue with your existing NutriSeeker experience.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="auth-form-panel">', unsafe_allow_html=True)
    st.markdown('<p class="step-kicker">Sign in</p><h2 class="step-title">Welcome back</h2><p class="step-copy">Log in to continue.</p>', unsafe_allow_html=True)

    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("Email", placeholder="alex@nutriseeker.app")
        password = st.text_input("Password", type="password", placeholder="Enter your password")
        submit = st.form_submit_button("Log In")

    if submit:
        if not is_valid_email(email):
            st.error("Enter a valid email address.")
        elif not password.strip():
            st.error("Enter your password.")
        else:
            auth_result = verify_user(email, password)
            if auth_result is False:
                st.error("Incorrect password.")
            elif auth_result is None:
                st.error("Account not found. Use Create Account first.")
            else:
                load_user_into_session(auth_result)
                st.session_state.logged_in = True
                set_screen("Home" if st.session_state.profile_ready else "Onboarding")
                st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Create Account", use_container_width=True, key="signup_preview"):
            if not is_valid_email(email):
                st.error("Enter a valid email address before creating an account.")
            elif not password.strip():
                st.error("Enter a password before creating an account.")
            elif get_user_by_email(email):
                st.error("An account with this email already exists. Log in instead.")
            else:
                display_name = email.split("@", 1)[0].replace(".", " ").replace("_", " ").title() if "@" in email else (email.strip().title() or "Alex")
                bundle = create_user(email, password, display_name or "Alex")
                load_user_into_session(bundle)
                st.session_state.logged_in = True
                st.session_state.onboarding_step = 1
                set_screen("Onboarding")
                st.rerun()
    with col2:
        if st.button("Explore Now", use_container_width=True, key="demo_preview"):
            start_guest_mode()
            st.rerun()
    st.markdown('<div class="subtle-note">By continuing you agree to the refreshed NutriSeeker experience.</div>', unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)


def render_onboarding_screen() -> None:
    selected_avatar = st.session_state.profile_avatar if st.session_state.profile_avatar in AVATAR_LOOKUP else "ava"
    step = st.session_state.onboarding_step
    wrapper_left, wrapper_mid, wrapper_right = st.columns([1, 1.35, 1], gap="large")
    with wrapper_mid:
        st.caption("Create your profile")
        st.subheader("Make NutriSeeker feel like yours")
        st.write("A short setup gives the app a proper identity: your name, a few optional details, and a premium avatar.")
        progress_cols = st.columns(3, gap="small")
        for idx, col in enumerate(progress_cols, start=1):
            with col:
                st.progress(100 if step >= idx else 0)

    if step == 1:
        with st.form("onboarding_name_form", clear_on_submit=False):
            name = st.text_input("Your name", value=st.session_state.display_name, placeholder="What should we call you?")
            submitted = st.form_submit_button("Continue")
        if submitted:
            if not name.strip():
                st.error("Name is required.")
            else:
                st.session_state.display_name = name.strip()
                st.session_state.onboarding_step = 2
                st.rerun()
    elif step == 2:
        with st.form("onboarding_details_form", clear_on_submit=False):
            age_input = st.text_input(
                "Age (optional)",
                value="" if st.session_state.profile_age is None else str(st.session_state.profile_age),
                placeholder="Example: 24",
            )
            gender = st.selectbox(
                "Gender (optional)",
                ["", "Female", "Male", "Non-binary", "Prefer not to say"],
                index=["", "Female", "Male", "Non-binary", "Prefer not to say"].index(st.session_state.profile_gender) if st.session_state.profile_gender in ["", "Female", "Male", "Non-binary", "Prefer not to say"] else 0,
            )
            left, right = st.columns(2)
            with left:
                back = st.form_submit_button("Back")
            with right:
                next_step = st.form_submit_button("Continue")
        if back:
            st.session_state.onboarding_step = 1
            st.rerun()
        if next_step:
            st.session_state.profile_age = int(age_input) if age_input.strip().isdigit() else None
            st.session_state.profile_gender = gender
            st.session_state.onboarding_step = 3
            st.rerun()
    else:
        st.write("Choose an avatar, or skip and NutriSeeker will assign a polished default for you.")
        render_avatar_selection(selected_avatar, key_prefix="onboard_avatar")
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            if st.button("Back", key="onboard_back", use_container_width=True):
                st.session_state.onboarding_step = 2
                st.rerun()
        with c2:
            if st.button("Skip for me", key="onboard_skip", use_container_width=True):
                save_profile_identity(st.session_state.display_name, st.session_state.profile_age, st.session_state.profile_gender, None)
                set_screen("Home")
                st.rerun()
        with c3:
            if st.button("Finish", key="onboard_finish", use_container_width=True):
                save_profile_identity(st.session_state.display_name, st.session_state.profile_age, st.session_state.profile_gender, selected_avatar)
                set_screen("Home")
                st.rerun()


def render_home_screen() -> None:
    user_logged_in = has_authenticated_user()
    summary = totals_for_day(dt.date.today()) if user_logged_in else empty_summary()
    latest = st.session_state.latest_analysis if user_logged_in else None
    recent_foods = all_recent_foods() if user_logged_in else []
    query = st.session_state.home_search.strip().lower()
    if query:
        recent_foods = [food for food in recent_foods if query in food["name"].lower()]
    greeting_name = st.session_state.display_name if user_logged_in else "Guest"
    subcopy = (
        "Analyze food images, review nutrition instantly, and keep your daily progress in a cleaner dashboard."
        if user_logged_in
        else "Browse the experience in guest mode. Sign in when you want to analyze meals and save your food history."
    )

    st.markdown(
        f"""
        <div class="home-hero screen-shell">
            <div class="home-hero-copy">
                <div class="pill" style="background:rgba(76,175,80,0.10); color:#2E7D32;">Hello, {html.escape(greeting_name)} 👋</div>
                <h2>Understand your meals. Improve your habits.</h2>
                <p>{html.escape(subcopy)}</p>
            </div>
            <div class="avatar-chip">{html.escape(greeting_name[:1].upper())}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="dashboard-grid screen-shell">', unsafe_allow_html=True)
    st.markdown('<div class="stack-gap">', unsafe_allow_html=True)
    render_summary_card(summary, "Calories Consumed", "Today's tracked calories")

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-head"><h3>Search recent foods</h3><span>Text only</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="search-shell">', unsafe_allow_html=True)
    st.text_input(
        "Search foods",
        key="home_search",
        placeholder="Search your recent foods",
        label_visibility="collapsed",
        disabled=not user_logged_in,
    )
    st.markdown("</div></div>", unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-head"><h3>Recent Foods</h3><span>Latest meals</span></div>', unsafe_allow_html=True)
    if user_logged_in and recent_foods:
        render_recent_foods(recent_foods)
    elif user_logged_in:
        render_empty_state_card(
            "No meals yet. Start by uploading your first meal.",
            "Your recent foods will appear here after your first analysis.",
        )
    else:
        render_empty_state_card(
            "No meals yet. Start by uploading your first meal.",
            "Explore mode never loads saved user logs.",
            badge="Guest mode",
        )
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="stack-gap">', unsafe_allow_html=True)
    st.markdown('<div class="action-card">', unsafe_allow_html=True)
    if user_logged_in:
        st.markdown('<h3>Analyze your meal</h3><p>Upload a food image, adjust portion size, and get nutrition results with the donut chart and meal explanation.</p>', unsafe_allow_html=True)
        if st.button("Open Meal Analyzer", key="home_open_add", use_container_width=True):
            set_screen("Add")
            st.rerun()
    else:
        st.markdown('<h3>Start tracking</h3><p>Create an account or sign in to analyze meals and save food history to your dashboard.</p>', unsafe_allow_html=True)
        if st.button("Sign In to Start Tracking", key="home_open_login", use_container_width=True):
            navigate_to("Login")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-head"><h3>Macronutrients</h3><span>Daily balance</span></div>', unsafe_allow_html=True)
    render_progress_row("Protein", summary["protein"], MACRO_GOALS["protein"], "linear-gradient(90deg, #4CAF50, #2E7D32)")
    render_progress_row("Carbs", summary["carbs"], MACRO_GOALS["carbs"], "linear-gradient(90deg, #9BD36B, #5AAE45)")
    render_progress_row("Fats", summary["fat"], MACRO_GOALS["fat"], "linear-gradient(90deg, #FFD15E, #F5B544)")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-head"><h3>Insights</h3><span>This week</span></div>', unsafe_allow_html=True)
    fig = weekly_chart()
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)
    donut = nutrition_donut(summary if latest else {"calories": 0, "protein": 0, "carbs": 0, "fat": 0})
    st.pyplot(donut, use_container_width=True)
    plt.close(donut)
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


def render_add_screen() -> None:
    st.markdown(
        """
        <div class="top-row screen-shell">
            <div class="greeting">
                <h1>Add a meal</h1>
                <p>Upload a food photo, fine-tune portion size, and keep the current backend analysis flow untouched.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="upload-preview-group screen-shell">', unsafe_allow_html=True)
    st.markdown('<div class="section-head"><h3>Meal Image</h3><span>Drag and drop preserved</span></div>', unsafe_allow_html=True)
    upload_col, preview_col = st.columns(2, gap="large")
    with upload_col:
        st.markdown('<p class="upload-pane-title">Upload</p>', unsafe_allow_html=True)
        uploaded_file = st.file_uploader(
            "Drag & drop or click to browse — JPG / JPEG / PNG",
            type=["jpg", "jpeg", "png"],
            label_visibility="visible",
        )
        if uploaded_file:
            st.caption(f"Selected file: {uploaded_file.name}")
    with preview_col:
        st.markdown('<p class="upload-pane-title">Preview</p>', unsafe_allow_html=True)
        if uploaded_file:
            render_image_preview(uploaded_file)
        else:
            st.markdown('<div class="empty-panel">Upload a meal image to see the preview here.</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-card screen-shell">', unsafe_allow_html=True)
    st.markdown('<div class="section-head"><h3>Meal details</h3><span>Text only</span></div>', unsafe_allow_html=True)
    st.markdown('<p class="field-label">🔎 Food name</p>', unsafe_allow_html=True)
    text_input = st.text_input(
        "Food name",
        placeholder="e.g. chicken biryani, dal makhani, masala dosa",
        label_visibility="collapsed",
    )
    st.markdown('<p class="field-label">🧠 Estimation mode</p>', unsafe_allow_html=True)
    portion_mode = st.radio(
        "Estimation mode",
        ["Default ⚡", "Model 🧠"],
        horizontal=True,
        label_visibility="collapsed",
        key="portion_mode_radio",
    )
    backend_mode = "default" if "Default" in portion_mode else "model"
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-card screen-shell">', unsafe_allow_html=True)
    st.markdown('<div class="section-head"><h3>Portion size</h3><span>Adjust precisely</span></div>', unsafe_allow_html=True)
    grams = st.session_state.portion_grams
    st.markdown(
        f"""
        <div class="hero-card" style="margin-bottom:0; background:linear-gradient(135deg, #ffffff 0%, #f1f8ee 100%); color:#18241d;">
            <div class="hero-copy">
                <div class="pill" style="background:rgba(76,175,80,0.10); color:#2E7D32;">Selected portion</div>
                <h2 style="color:#18241d;">{grams}<span style="font-size:1rem; color:#6b7b69;"> g</span></h2>
                <p style="color:#6b7b69;">{portion_tag(grams)} serving</p>
            </div>
            <div class="avatar-chip" style="width:76px; height:76px; border-radius:24px;">⚖️</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.slider(
        "Slide to adjust grams",
        min_value=0,
        max_value=1000,
        step=5,
        value=st.session_state.portion_grams,
        key="_slider_val",
        on_change=on_slider_change,
        label_visibility="collapsed",
    )
    number_col, unit_col = st.columns([4, 1])
    with number_col:
        st.number_input(
            "Or type exact grams",
            min_value=0,
            max_value=1000,
            step=10,
            value=st.session_state.portion_grams,
            key="_input_val",
            on_change=on_input_change,
            label_visibility="visible",
        )
    with unit_col:
        st.markdown('<div style="padding-top:2rem;color:#6b7b69;font-weight:700;">/ 1000g</div>', unsafe_allow_html=True)

    chip_cols = st.columns(5)
    preset_values = [("75g", 75), ("150g", 150), ("250g", 250), ("500g", 500), ("1kg", 1000)]
    for column, (label, value) in zip(chip_cols, preset_values):
        with column:
            if st.button(label, key=f"preset_{value}"):
                st.session_state.portion_grams = value
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    analyze_btn = st.button("Analyze Meal", type="primary", use_container_width=True)
    if analyze_btn:
        if uploaded_file is None:
            st.error("Please upload a food image first.")
        else:
            with st.spinner("Analyzing your meal..."):
                try:
                    response = requests.post(
                        f"{API_URL}/analyze-meal",
                        files={"image": ("image.jpg", uploaded_file.getvalue(), "image/jpeg")},
                        data={
                            "text": text_input,
                            "grams": st.session_state.portion_grams,
                            "mode": backend_mode,
                        },
                        timeout=120,
                    )
                    if response.status_code != 200:
                        st.error(explain_backend_response(response))
                    else:
                        data = response.json()
                        if "error" in data:
                            st.error(str(data["error"]))
                        else:
                            add_history_entry(data, text_input)
                            set_screen("Results")
                            st.success("Analysis complete.")
                            st.rerun()
                except requests.exceptions.ConnectionError:
                    st.error("Cannot connect to API. Make sure FastAPI is running on port 8000.")
                except Exception as exc:
                    st.error(f"Error: {exc}")

    latest = st.session_state.latest_analysis
    if latest:
        summary = latest["summary"]
        st.markdown('<div class="section-card screen-shell">', unsafe_allow_html=True)
        st.markdown('<div class="section-head"><h3>Latest result</h3><span>Per analyzed meal</span></div>', unsafe_allow_html=True)
        kcal_col, protein_col, carbs_col = st.columns(3)
        kcal_col.metric("Calories", f"{summary['calories']:.0f} kcal")
        protein_col.metric("Protein", f"{summary['protein']:.1f}g")
        carbs_col.metric("Carbs", f"{summary['carbs']:.1f}g")
        fat_col, fiber_col = st.columns(2)
        fat_col.metric("Fats", f"{summary['fat']:.1f}g")
        fiber_col.metric("Fiber", f"{summary['fiber']:.1f}g")
        if latest["raw_output"]:
            st.write(f"Detected: {clean_text(latest['raw_output'])}")
        if latest["results"]:
            for item in latest["results"]:
                render_meal_card(
                    safe_food_title(item),
                    f"Protein {float(item.get('protein', 0)):.1f}g · Carbs {float(item.get('carbs', 0)):.1f}g · Fats {float(item.get('fat', 0)):.1f}g",
                    float(item.get("calories", 0)),
                )
        st.markdown("</div>", unsafe_allow_html=True)


def render_results_screen() -> None:
    latest = st.session_state.latest_analysis
    st.markdown(
        """
        <div class="top-row screen-shell">
            <div class="greeting">
                <h1>Results</h1>
                <p>Your most recent analysis with food breakdown, donut chart, and explainable guidance.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not latest:
        st.markdown('<div class="empty-panel">No analyzed meal yet. Use Add to upload a food image and generate results.</div>', unsafe_allow_html=True)
        return

    summary = latest["summary"]
    analyzed_at = dt.datetime.fromisoformat(latest["timestamp"]).strftime("%b %d, %I:%M %p")
    render_summary_card(summary, "Latest Analysis", analyzed_at)

    left_col, right_col = st.columns([1.15, 0.85], gap="large")

    with left_col:
        item_count = len(latest["results"])
        st.markdown(f'<div class="section-card screen-shell"><div class="section-head"><h3>Detected Foods</h3><span>{analyzed_at}</span></div><p class="detected-summary">{item_count} item{"s" if item_count != 1 else ""} detected</p></div>', unsafe_allow_html=True)
        if latest["results"]:
            for item in latest["results"]:
                food_name = safe_food_title(item)
                with st.expander(food_name, expanded=False):
                    st.markdown(
                        f"""
                        <div class="nutrient-grid">
                            <div class="nutrient-chip calories">
                                <span>🔥 Calories</span>
                                <strong>{float(item.get('calories', 0)):.0f} kcal</strong>
                            </div>
                            <div class="nutrient-chip protein">
                                <span>🏋️ Protein</span>
                                <strong>{float(item.get('protein', 0)):.1f} g</strong>
                            </div>
                            <div class="nutrient-chip carbs">
                                <span>🌾 Carbohydrates</span>
                                <strong>{float(item.get('carbs', 0)):.1f} g</strong>
                            </div>
                            <div class="nutrient-chip fats">
                                <span>💧 Fats</span>
                                <strong>{float(item.get('fat', 0)):.1f} g</strong>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        else:
            st.markdown('<div class="empty-panel">No food items were returned in the latest analysis.</div>', unsafe_allow_html=True)
        if latest["raw_output"]:
            st.caption(f"Detected output: {clean_text(latest['raw_output'])}")

        explanation = "".join(f"<li>{line}</li>" for line in explain_latest_analysis())
        st.markdown(
            f"""
            <div class="explain-card screen-shell">
                <div class="section-head"><h3>Explainable AI</h3><span>Profile-aware</span></div>
                <ol>{explanation}</ol>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right_col:
        st.markdown('<div class="section-head screen-shell"><h3>Macro donut</h3><span>Latest meal</span></div>', unsafe_allow_html=True)
        donut = nutrition_donut(summary)
        st.pyplot(donut, use_container_width=True)
        plt.close(donut)

        st.markdown(f'<div class="section-head screen-shell"><h3>Meal totals</h3><span>{latest["grams"]}g analyzed</span></div>', unsafe_allow_html=True)
        kcal_col, protein_col, carbs_col = st.columns(3)
        kcal_col.metric("Calories", f"{summary['calories']:.0f} kcal")
        protein_col.metric("Protein", f"{summary['protein']:.1f}g")
        carbs_col.metric("Carbs", f"{summary['carbs']:.1f}g")
        fat_col, fiber_col = st.columns(2)
        fat_col.metric("Fats", f"{summary['fat']:.1f}g")
        fiber_col.metric("Fiber", f"{summary['fiber']:.1f}g")


def render_diary_screen() -> None:
    selected_date = st.session_state.selected_date
    display_month = st.session_state.display_month

    st.markdown(
        """
        <div class="top-row screen-shell">
            <div class="greeting">
                <h1>Diary</h1>
                <p>Monthly view with daily calorie and macro summaries.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    nav_left, nav_mid, nav_right = st.columns([1, 3, 1])
    with nav_left:
        if st.button("‹", key="prev_month"):
            st.session_state.display_month = month_shift(display_month, -1)
            st.rerun()
    with nav_mid:
        st.markdown(
            f"<div style='text-align:center;padding-top:0.8rem;font-weight:800;color:#18241d;'>{display_month.strftime('%B %Y')}</div>",
            unsafe_allow_html=True,
        )
    with nav_right:
        if st.button("›", key="next_month"):
            st.session_state.display_month = month_shift(display_month, 1)
            st.rerun()

    picked = st.date_input("Selected day", value=selected_date, key="selected_date_picker")
    if picked != selected_date:
        st.session_state.selected_date = picked
        st.session_state.display_month = picked.replace(day=1)
        selected_date = picked
        display_month = st.session_state.display_month

    st.markdown('<div class="calendar-card screen-shell">', unsafe_allow_html=True)
    st.markdown(render_calendar_html(st.session_state.selected_date, st.session_state.display_month), unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    daily_summary = totals_for_day(st.session_state.selected_date)
    subtitle = st.session_state.selected_date.strftime("%A, %B %d")
    render_summary_card(daily_summary, "Daily Summary", subtitle)

    st.markdown('<div class="section-card screen-shell">', unsafe_allow_html=True)
    st.markdown('<div class="section-head"><h3>Meals</h3><span>Selected day</span></div>', unsafe_allow_html=True)
    day_entries = entries_for_day(st.session_state.selected_date)
    if day_entries:
        grouped = {}
        for entry in day_entries:
            grouped.setdefault(entry["meal_bucket"], []).append(entry)
        for bucket in ["Breakfast", "Lunch", "Snacks", "Dinner"]:
            if bucket not in grouped:
                continue
            st.markdown(f"<p class='field-label'>{bucket}</p>", unsafe_allow_html=True)
            for entry in grouped[bucket]:
                title = ", ".join(clean_text(food, fallback="Meal") for food in entry["foods"][:2])
                if len(entry["foods"]) > 2:
                    title += f" +{len(entry['foods']) - 2} more"
                render_meal_card(
                    title,
                    f"{entry['grams']}g analyzed · {dt.datetime.fromisoformat(entry['timestamp']).strftime('%I:%M %p')}",
                    entry["summary"]["calories"],
                )
    else:
        st.markdown('<div class="empty-panel">No meals logged for the selected day yet.</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_insights_screen() -> None:
    summary = totals_for_day(dt.date.today())
    macro_mix = macro_percentages(summary)
    st.markdown(
        """
        <div class="top-row screen-shell">
            <div class="greeting">
                <h1>Insights</h1>
                <p>Weekly calorie trends and macro distribution from your analyzed meals.</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="kpi-grid screen-shell" style="margin-bottom:1rem;">
            <div class="kpi-card"><span>This week</span><strong>{sum(weekly_calorie_series()[1]):.0f}</strong><span>tracked kcal</span></div>
            <div class="kpi-card"><span>Meals logged</span><strong>{len(st.session_state.analysis_history)}</strong><span>session total</span></div>
            <div class="kpi-card"><span>Protein mix</span><strong>{macro_mix['protein']}%</strong><span>of tracked macros</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-card screen-shell">', unsafe_allow_html=True)
    st.markdown('<div class="section-head"><h3>Calories trend</h3><span>Last 7 days</span></div>', unsafe_allow_html=True)
    fig = weekly_chart()
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="section-card screen-shell">', unsafe_allow_html=True)
    st.markdown('<div class="section-head"><h3>Macro distribution</h3><span>Today</span></div>', unsafe_allow_html=True)
    left, right = st.columns([3, 2])
    with left:
        donut = nutrition_donut(summary)
        st.pyplot(donut, use_container_width=True)
        plt.close(donut)
    with right:
        render_progress_row("Protein", summary["protein"], MACRO_GOALS["protein"], "linear-gradient(90deg, #4CAF50, #2E7D32)")
        render_progress_row("Carbs", summary["carbs"], MACRO_GOALS["carbs"], "linear-gradient(90deg, #9BD36B, #5AAE45)")
        render_progress_row("Fats", summary["fat"], MACRO_GOALS["fat"], "linear-gradient(90deg, #FFD15E, #F5B544)")
    st.markdown("</div>", unsafe_allow_html=True)


def render_profile_screen() -> None:
    ensure_avatar_selected()
    today_summary = totals_for_day(dt.date.today())
    meals_today = len(entries_for_day(dt.date.today()))
    history_total = len(st.session_state.analysis_history)
    snapshot = profile_snapshot()
    target = calorie_target_from_profile()
    bmi = bmi_snapshot()
    st.subheader("Profile")
    if st.session_state.profile_flash:
        st.success(st.session_state.profile_flash)
        st.session_state.profile_flash = ""
    st.markdown('<div class="profile-dashboard">', unsafe_allow_html=True)
    left_col, right_col = st.columns(2, gap="large")
    with left_col:
        st.markdown(
            f"""
            <div class="profile-panel-card">
                <div class="profile-avatar-wrap">
                    <div style="
                        width:108px;
                        height:108px;
                        margin:0 auto;
                        border-radius:999px;
                        display:flex;
                        align-items:center;
                        justify-content:center;
                        background:linear-gradient(180deg,#ffffff,#eef6ea);
                        border:1px solid rgba(83,118,80,0.10);
                        box-shadow:0 18px 34px rgba(46,125,50,0.10);
                        font-size:64px;
                        line-height:1;
                    ">{avatar_emoji(snapshot['avatar'])}</div>
                    <div class="profile-edit-chip">Edit</div>
                </div>
                <p class="profile-title">{snapshot['name']} 👋</p>
                <p class="profile-subtitle">{profile_tagline()}</p>
                <div class="profile-stat-grid">
                    <div class="profile-stat-item"><span>Today's kcal</span><strong>{today_summary['calories']:.0f}</strong></div>
                    <div class="profile-stat-item"><span>Meals tracked</span><strong>{meals_today}</strong></div>
                    <div class="profile-stat-item"><span>History</span><strong>{history_total}</strong></div>
                </div>
                <div class="profile-pill-row">
                    <div class="profile-pill">Age: {snapshot['age']}</div>
                    <div class="profile-pill">Gender: {snapshot['gender']}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.popover("Change Avatar", use_container_width=True):
            st.write("Choose a new avatar")
            render_avatar_selection(snapshot["avatar"], key_prefix="profile_avatar")
        st.markdown('<div class="profile-section-card">', unsafe_allow_html=True)
        st.info(f"Estimated daily calorie target: {target:.0f} kcal")
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="profile-section-card">', unsafe_allow_html=True)
        if bmi:
            bmi_text = f"{bmi['icon']} BMI: {bmi['bmi']:.1f} ({bmi['category']})"
            if bmi["tone"] == "success":
                st.success(bmi_text)
            elif bmi["tone"] == "error":
                st.error(bmi_text)
            else:
                st.warning(bmi_text)
        else:
            st.info("BMI unavailable. Enter height and weight in Health Metrics.")
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="profile-section-card">', unsafe_allow_html=True)
        with st.expander("Explainable AI preview", expanded=True):
            for line in explain_latest_analysis():
                st.write(f"- {line}")
        st.markdown('</div>', unsafe_allow_html=True)

    with right_col:
        st.markdown('<div class="profile-column-stack">', unsafe_allow_html=True)
        st.markdown("#### Personalization")
        st.caption("Keep identity and health metrics updated for more accurate recommendations.")
        st.markdown('<div class="profile-section-card">', unsafe_allow_html=True)
        with st.form("profile_identity_form", clear_on_submit=False):
            st.write("Identity")
            name = st.text_input("Name", value=snapshot["name"])
            age_input = st.text_input("Age", value="" if st.session_state.profile_age is None else str(st.session_state.profile_age), placeholder="Optional")
            gender_options = ["", "Female", "Male", "Non-binary", "Prefer not to say"]
            gender = st.selectbox(
                "Gender",
                gender_options,
                index=gender_options.index(st.session_state.profile_gender) if st.session_state.profile_gender in gender_options else 0,
            )
            save_identity = st.form_submit_button("Save Identity")
        if save_identity:
            if not name.strip():
                st.error("Name is required.")
            else:
                save_profile_identity(name, age_input, gender, snapshot["avatar"])
                st.success("Profile updated.")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="profile-section-card">', unsafe_allow_html=True)
        with st.form("profile_guidance_form", clear_on_submit=False):
            st.write("Health Metrics")
            st.caption("Enter your body data for personalized nutrition insights")
            c1, c2 = st.columns(2)
            with c1:
                height_input = st.text_input(
                    "Height (cm)",
                    value="" if st.session_state.profile_height_cm is None else str(st.session_state.profile_height_cm),
                    placeholder="Enter your height",
                )
                activity_levels = ["Low", "Moderate", "High"]
                current_activity = st.session_state.profile_activity if st.session_state.profile_activity in activity_levels else "Moderate"
                activity = st.selectbox("Activity Level", activity_levels, index=activity_levels.index(current_activity))
            with c2:
                weight_input = st.text_input(
                    "Weight (kg)",
                    value="" if st.session_state.profile_weight_kg is None else str(st.session_state.profile_weight_kg),
                    placeholder="Enter your weight",
                )
                goal = st.selectbox("Goal", ["Lose", "Maintain", "Gain"], index=["Lose", "Maintain", "Gain"].index(st.session_state.profile_goal))
            save_guidance = st.form_submit_button("Save Health Data")
        if save_guidance:
            try:
                parsed_height = float(height_input.strip()) if height_input.strip() else None
                parsed_weight = float(weight_input.strip()) if weight_input.strip() else None
            except ValueError:
                parsed_height = None
                parsed_weight = None
            if parsed_height is None or parsed_weight is None:
                st.error("Please enter valid numeric values for height and weight.")
            elif parsed_height < 100 or parsed_height > 230:
                st.error("Height should be between 100 and 230 cm.")
            elif parsed_weight < 30 or parsed_weight > 250:
                st.error("Weight should be between 30 and 250 kg.")
            else:
                st.session_state.profile_height_cm = round(parsed_height, 1)
                st.session_state.profile_weight_kg = round(parsed_weight, 1)
                st.session_state.profile_activity = activity
                st.session_state.profile_goal = goal
                if st.session_state.current_user_id:
                    update_profile_guidance(
                        st.session_state.current_user_id,
                        st.session_state.profile_height_cm,
                        st.session_state.profile_weight_kg,
                        st.session_state.profile_activity,
                        st.session_state.profile_goal,
                    )
                st.session_state.profile_flash = "Health data saved and insights refreshed."
                st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


inject_css()
render_background_scene()

st.markdown('<div class="page-shell"><div class="content-panel">', unsafe_allow_html=True)

if not has_authenticated_user() and not st.session_state.guest_mode:
    render_login_screen()
    st.markdown('</div></div>', unsafe_allow_html=True)
    st.stop()

if st.session_state.guest_mode and st.session_state.active_screen != "Home":
    set_screen("Home")

if has_authenticated_user() and not st.session_state.profile_ready and st.session_state.active_screen != "Onboarding":
    set_screen("Onboarding")

render_brand()
if st.session_state.active_screen == "Onboarding":
    render_onboarding_screen()
elif st.session_state.active_screen == "Home":
    render_home_screen()
elif st.session_state.active_screen == "Diary":
    render_diary_screen()
elif st.session_state.active_screen == "Add":
    render_add_screen()
elif st.session_state.active_screen == "Results":
    render_results_screen()
elif st.session_state.active_screen == "Insights":
    render_insights_screen()
else:
    render_profile_screen()

st.markdown('</div></div>', unsafe_allow_html=True)
