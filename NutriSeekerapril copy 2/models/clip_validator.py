# -*- coding: utf-8 -*-
from transformers import CLIPProcessor, CLIPModel
from PIL import Image
import torch

print("⏳ Loading CLIP model...")
clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
print("✅ CLIP loaded!")

def validate_food(image: Image.Image) -> bool:
    """
    Returns True if image contains food.
    Returns False if not food.
    """
    inputs = clip_processor(
        images=image,
        text=["a photo of food", "a photo of not food"],
        return_tensors="pt",
        padding=True
    )

    with torch.no_grad():
        outputs = clip_model(**inputs)

    probs = outputs.logits_per_image.softmax(dim=1)
    food_prob = probs[0][0].item()
    not_food_prob = probs[0][1].item()

    print(f"Food probability: {food_prob:.2f}")
    print(f"Not food probability: {not_food_prob:.2f}")

    return food_prob > not_food_prob