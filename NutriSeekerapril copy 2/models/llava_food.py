import requests
import base64
from PIL import Image
import io

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llava"  # whatever ollama list shows

def pil_to_base64(pil_image):
    buffer = io.BytesIO()
    pil_image.save(buffer, format="JPEG")
    buffer.seek(0)
    return base64.b64encode(buffer.read()).decode("utf-8")

def validate_food(image: Image.Image) -> bool:
    img_b64 = pil_to_base64(image)
    payload = {
        "model": MODEL_NAME,
        "prompt": "Does this image contain food or a meal? Answer with only one word: YES or NO",
        "images": [img_b64],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 5}
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=30)
        answer = response.json()["response"].strip().upper()
        print(f"Food validator: {answer}")
        return "YES" in answer
    except requests.exceptions.ConnectionError:
        print("❌ Ollama not running!")
        return False

def identify_food(image: Image.Image):
    import re
    img_b64 = pil_to_base64(image)
    payload = {
        "model": MODEL_NAME,
        "prompt": """Look at this food image carefully.
List all unique food items you can see.
Format exactly like this:
FOODS: item1, item2, item3
Only list food names, no descriptions.""",
        "images": [img_b64],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 100}
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        raw_output = response.json().get("response", "")
        print(f"LLaVA raw: {raw_output}")

        foods = []
        # Try to find "FOODS:" pattern
        match = re.search(r"FOODS:\s*(.*)", raw_output, re.IGNORECASE | re.DOTALL)
        if match:
            content = match.group(1).strip()
            # Split by common separators
            foods = [f.strip().lower() for f in re.split(r'[,;•\n]', content)]
        else:
            # Fallback: Parse line by line and clean up markers
            lines = raw_output.strip().split("\n")
            for line in lines:
                # Remove common list markers like "1.", "-", "*", "•"
                clean = re.sub(r'^[-\*\d\.\•\s]+', '', line).strip()
                if clean and len(clean) < 30: # Avoid long sentences
                    foods.append(clean.lower())

        # Final cleanup: remove empty, duplicates and limit to 5
        seen = set()
        final_foods = []
        for f in foods:
            if f and f not in seen:
                final_foods.append(f)
                seen.add(f)
        
        final_foods = final_foods[:5]
        print(f"Detected: {final_foods}")
        return final_foods, raw_output

    except Exception as e:
        print(f"❌ Food detection error: {e}")
        return [], str(e)

def estimate_portion(image: Image.Image):
    img_b64 = pil_to_base64(image)
    payload = {
        "model": MODEL_NAME,
        "prompt": """How much food is in this image?
Small = less than 100g
Medium = 100-200g
Large = more than 200g
Answer one word only: SMALL, MEDIUM or LARGE""",
        "images": [img_b64],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 10}
    }
    PORTION_MAP = {
        "SMALL":  ("Small (~75g)", 75),
        "MEDIUM": ("Medium (~150g)", 150),
        "LARGE":  ("Large (~250g)", 250)
    }
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=30)
        answer = response.json()["response"].strip().upper()
        print(f"Portion: {answer}")
        for key in PORTION_MAP:
            if key in answer:
                return PORTION_MAP[key]
        return PORTION_MAP["MEDIUM"]
    except:
        return ("Medium (~150g)", 150)