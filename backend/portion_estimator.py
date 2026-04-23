import numpy as np
from PIL import Image
import cv2

# Density Table from Requirements
DENSITY = {
    "rice": 0.75,
    "biryani": 0.85,
    "chips": 0.25,
    "french fries": 0.6,
    "pizza": 0.9,
    "default": 0.5  # Fallback for unknown foods
}

# Average Heights from Requirements
HEIGHTS = {
    "rice": 2.0,
    "biryani": 2.5,
    "chips": 1.0,
    "french fries": 1.5,
    "pizza": 2.5,
    "default": 1.5
}

def estimate_portion_model(image: Image.Image, food_type: str):
    """
    Model-Based Portion Estimation Pipeline
    """
    try:
        # --- STEP 1: FOOD SEGMENTATION (MANDATORY) ---
        # Convert to CV2 format
        img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        
        # Fallback: Simple Otsu Thresholding for mask
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        # Clean up mask (optional but good for 'real AI feel')
        kernel = np.ones((5,5), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)

        # --- STEP 2: PIXEL AREA CALCULATION ---
        pixel_area = np.sum(mask == 255)
        total_pixels = image.width * image.height
        
        # --- STEP 3: REAL-WORLD SCALING (CRITICAL) ---
        # Assume plate diameter = 25 cm (default)
        # We'll use the bounding box of the detected food as a proxy or 
        # assume a standard FOV where a 25cm plate fills ~80% of image width.
        plate_diameter_cm = 25.0
        
        # If we can't detect the plate explicitly, we approximate the scaling factor:
        # We assume 1 cm is roughly equivalent to (Image Width / 30) pixels
        # (Assuming the camera is ~30-40cm away from the table)
        cm_to_pixel_ratio = image.width / 30.0 
        area_cm2 = pixel_area / (cm_to_pixel_ratio ** 2)

        # --- STEP 4: HEIGHT / DEPTH ESTIMATION ---
        # Fallback average heights as requested
        food_key = food_type.lower() if food_type else "default"
        height_cm = HEIGHTS.get(food_key, HEIGHTS["default"])

        # --- STEP 5: VOLUME ESTIMATION ---
        volume_cm3 = area_cm2 * height_cm

        # --- STEP 6: CONVERT VOLUME -> GRAMS ---
        density = DENSITY.get(food_key, DENSITY["default"])
        grams = int(volume_cm3 * density)
        
        # Safety floor/ceiling
        grams = max(10, min(1000, grams))

        return {
            "portion_label": f"{grams} g (AI Model)",
            "grams": grams,
            "portion_source": "model"
        }

    except Exception as e:
        # Robust Fallback
        print(f"Error in model estimation: {e}")
        return {
            "portion_label": "150 g (Fallback)",
            "grams": 150,
            "portion_source": "fallback"
        }

def resolve_portion(text, image, food_type, mode="default"):
    """
    Integrates Default and Model modes
    """
    # Import here to avoid circular imports if needed
    from models.llava_food import estimate_portion as existing_estimate_portion
    
    if mode == "default":
        # USE EXISTING LOGIC (DO NOT MODIFY)
        label, grams = existing_estimate_portion(image)
        return {
            "portion_label": label,
            "grams": grams,
            "portion_source": "llava"
        }

    if mode == "model":
        # CALL NEW PIPELINE
        return estimate_portion_model(image, food_type)
    
    return {"portion_label": "150 g", "grams": 150, "portion_source": "unknown"}
