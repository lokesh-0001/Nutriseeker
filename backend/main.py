import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.clip_validator import validate_food
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io

from models.llava_food import identify_food
from backend.portion_estimator import resolve_portion
from config.settings import ALLOWED_ORIGINS
from database.nutrition import get_nutrition

app = FastAPI(title="NutriSeeker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/")
def root():
    return {"status": "NutriSeeker API running ✅"}

@app.post("/validate-food")
async def api_validate(image: UploadFile = File(...)):
    img = Image.open(io.BytesIO(await image.read()))
    return {"is_food": validate_food(img)}

@app.post("/analyze-meal")
async def api_analyze(
    image: UploadFile = File(...),
    text: str = Form(default=""),
    grams: int = Form(default=0),
    mode: str = Form(default="default")
):
    img = Image.open(io.BytesIO(await image.read()))

    # Step 1 — CLIP Food Validator
    if not validate_food(img):
        return {"error": "❌ Not a food image. Please upload a photo of food."}

    # Step 2 — LLaVA identifies foods
    foods, raw = identify_food(img)

    # Step 3 — Resolve Portion
    primary_food = text.strip() if text.strip() else (foods[0] if foods else "food")
    portion_data = resolve_portion(text, img, primary_food, mode=mode)
    
    portion_label = portion_data["portion_label"]
    estimated_grams = portion_data["grams"]

    # --- PORTION PRIORITIZATION LOGIC ---
    if mode == "model":
        # In Model mode, we ALWAYS use the AI-calculated grams
        final_grams = estimated_grams
    else:
        # In Default mode, respect manual slider overrides
        if grams and grams > 0:
            final_grams = grams
            portion_label = f"Custom ({grams}g)"
        else:
            final_grams = estimated_grams

    # Step 4 — Text override for food name
    if text.strip():
        foods = [text.strip().lower()]

    # Step 5 — Scale nutrition by portion (IFCT values are per 100g)
    multiplier = final_grams / 100
    results = []
    for food in foods:
        nutrition = get_nutrition(food)
        if nutrition:
            results.append({
                "food":       nutrition['food'],
                "source":     nutrition['source'],
                "calories":   round(nutrition['calories']           * multiplier, 1),
                "protein":    round(nutrition['protein']            * multiplier, 1),
                "carbs":      round(nutrition['carbs']              * multiplier, 1),
                "fat":        round(nutrition['fat']                * multiplier, 1),
                "fiber":      round(nutrition['fiber']              * multiplier, 1),
                "sodium":     round(nutrition.get('sodium',    0)   * multiplier, 1),
                "calcium":    round(nutrition.get('calcium',   0)   * multiplier, 1),
                "iron":       round(nutrition.get('iron',      0)   * multiplier, 2),
                "vitamin_c":  round(nutrition.get('vitamin_c', 0)   * multiplier, 1),
                "potassium":  round(nutrition.get('potassium', 0)   * multiplier, 1),
                "magnesium":  round(nutrition.get('magnesium', 0)   * multiplier, 1),
                "zinc":       round(nutrition.get('zinc',      0)   * multiplier, 2),
                "thiamine":   round(nutrition.get('thiamine',  0)   * multiplier, 3),
                "riboflavin": round(nutrition.get('riboflavin',0)   * multiplier, 3),
                "niacin":     round(nutrition.get('niacin',    0)   * multiplier, 2),
                "vitamin_b6": round(nutrition.get('vitamin_b6',0)   * multiplier, 3),
                "folate":     round(nutrition.get('folate',    0)   * multiplier, 1),
                "vitamin_a":  round(nutrition.get('vitamin_a', 0)   * multiplier, 1),
                "vitamin_e":  round(nutrition.get('vitamin_e', 0)   * multiplier, 2),
                "phosphorus": round(nutrition.get('phosphorus',0)   * multiplier, 1),
                "manganese":  round(nutrition.get('manganese', 0)   * multiplier, 3),
            })

    return {
        "raw_output":  raw,
        "foods":       foods,
        "portion":     portion_label,
        "grams":       final_grams,
        "results":     results
    }

@app.get("/get-nutrients")
async def api_nutrients(food_name: str):
    result = get_nutrition(food_name)
    if result:
        return result
    return {"error": "Food not found"}
