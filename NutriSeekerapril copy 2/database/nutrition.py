import pandas as pd
import numpy as np
import requests
from sentence_transformers import SentenceTransformer
import faiss
import os

# ── Load INDB ──────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "indb.csv")

df = pd.read_csv(CSV_PATH)
print(f"✅ INDB loaded! {len(df)} foods")

# Keep only columns we need
cols_needed = [
    'food_code', 'food_name',
    # Macros
    'energy_kcal', 'protein_g', 'carb_g', 'fat_g', 'fibre_g',
    # Minerals
    'sodium_mg', 'calcium_mg', 'iron_mg', 'potassium_mg',
    'magnesium_mg', 'zinc_mg', 'phosphorus_mg', 'manganese_mg',
    # Vitamins
    'vitc_mg', 'vita_ug', 'vite_mg', 'vitb6_mg',
    'vitb1_mg', 'vitb2_mg', 'vitb3_mg', 'folate_ug',
]
df = df[cols_needed].fillna(0)

# ── Build FAISS Index ───────────────────────────────
print("⏳ Building FAISS index...")
embedder = SentenceTransformer('all-MiniLM-L6-v2')
food_names = df['food_name'].tolist()
embeddings = np.array(embedder.encode(food_names)).astype('float32')

index = faiss.IndexFlatL2(embeddings.shape[1])
index.add(embeddings)
print(f"✅ FAISS index built! {len(food_names)} foods indexed")

# ── Helper to build return dict from a row ──────────
def build_result(data, source="INDB"):
    return {
        "source": source,
        "food": data['food_name'],
        # Macros
        "calories":   round(float(data['energy_kcal']), 1),
        "protein":    round(float(data['protein_g']), 1),
        "carbs":      round(float(data['carb_g']), 1),
        "fat":        round(float(data['fat_g']), 1),
        "fiber":      round(float(data['fibre_g']), 1),
        # Minerals
        "sodium":     round(float(data['sodium_mg']), 1),
        "calcium":    round(float(data['calcium_mg']), 1),
        "iron":       round(float(data['iron_mg']), 2),
        "potassium":  round(float(data['potassium_mg']), 1),
        "magnesium":  round(float(data['magnesium_mg']), 1),
        "zinc":       round(float(data['zinc_mg']), 2),
        "phosphorus": round(float(data['phosphorus_mg']), 1),
        "manganese":  round(float(data['manganese_mg']), 3),
        # Vitamins
        "vitamin_c":  round(float(data['vitc_mg']), 1),
        "vitamin_a":  round(float(data['vita_ug']), 1),
        "vitamin_e":  round(float(data['vite_mg']), 2),
        "vitamin_b6": round(float(data['vitb6_mg']), 3),
        "thiamine":   round(float(data['vitb1_mg']), 3),
        "riboflavin": round(float(data['vitb2_mg']), 3),
        "niacin":     round(float(data['vitb3_mg']), 2),
        "folate":     round(float(data['folate_ug']), 1),
    }

# ── Search INDB ─────────────────────────────────────
def search_indb(food_name: str):
    food_name = food_name.lower().strip()
    query_vec = np.array(
        embedder.encode([food_name])
    ).astype('float32')

    distances, indices = index.search(query_vec, 3)
    best_idx = indices[0][0]
    best_dist = distances[0][0]

    print(f"FAISS: '{food_name}' → '{df.iloc[best_idx]['food_name']}' (dist={best_dist:.2f})")

    if best_dist > 0.8:
        print(f"⚠️ No close INDB match (dist={best_dist:.2f})")
        return None

    return build_result(df.iloc[best_idx])

# ── Search USDA ─────────────────────────────────────
def search_usda(food_name: str):
    try:
        url = "https://api.nal.usda.gov/fdc/v1/foods/search"
        params = {
            "query": food_name,
            "api_key": "DEMO_KEY",
            "pageSize": 1
        }
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        if data.get('foods'):
            food = data['foods'][0]
            nutrients = {
                n['nutrientName']: n['value']
                for n in food.get('foodNutrients', [])
            }
            return {
                "source": "USDA",
                "food": food['description'],
                "calories":  round(nutrients.get('Energy', 0), 1),
                "protein":   round(nutrients.get('Protein', 0), 1),
                "carbs":     round(nutrients.get('Carbohydrate, by difference', 0), 1),
                "fat":       round(nutrients.get('Total lipid (fat)', 0), 1),
                "fiber":     round(nutrients.get('Fiber, total dietary', 0), 1),
                "sodium":    round(nutrients.get('Sodium, Na', 0), 1),
                "calcium":   round(nutrients.get('Calcium, Ca', 0), 1),
                "iron":      round(nutrients.get('Iron, Fe', 0), 2),
                "potassium": round(nutrients.get('Potassium, K', 0), 1),
                "magnesium": round(nutrients.get('Magnesium, Mg', 0), 1),
                "zinc":      round(nutrients.get('Zinc, Zn', 0), 2),
                "phosphorus":round(nutrients.get('Phosphorus, P', 0), 1),
                "manganese": round(nutrients.get('Manganese, Mn', 0), 3),
                "vitamin_c": round(nutrients.get('Vitamin C, total ascorbic acid', 0), 1),
                "vitamin_a": round(nutrients.get('Vitamin A, RAE', 0), 1),
                "vitamin_e": round(nutrients.get('Vitamin E (alpha-tocopherol)', 0), 2),
                "vitamin_b6":round(nutrients.get('Vitamin B-6', 0), 3),
                "thiamine":  round(nutrients.get('Thiamin', 0), 3),
                "riboflavin":round(nutrients.get('Riboflavin', 0), 3),
                "niacin":    round(nutrients.get('Niacin', 0), 2),
                "folate":    round(nutrients.get('Folate, total', 0), 1),
            }
    except:
        pass
    return None

# ── Master Function ──────────────────────────────────
def get_nutrition(food_name: str):
    result = search_indb(food_name)
    if result:
        print("✅ Found in INDB!")
        return result
    print("⚠️ Trying USDA...")
    result = search_usda(food_name)
    if result:
        print("✅ Found in USDA!")
        return result
    return None