from PIL import Image
from llava_food import validate_food, identify_food, estimate_portion

img = Image.open("test.jpg")

print("\n--- Validator ---")
print(validate_food(img))

print("\n--- Identifier ---")
foods, raw = identify_food(img)
print(foods)

print("\n--- Portion ---")
print(estimate_portion(img))