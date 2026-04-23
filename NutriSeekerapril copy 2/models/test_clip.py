# -*- coding: utf-8 -*-
from PIL import Image
from clip_validator import validate_food

# Test with food image
food_img = Image.open("test.jpeg")
print(f"Food image result: {validate_food(food_img)}")  # Should be True