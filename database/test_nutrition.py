from nutrition import get_nutrition

test_foods = ["rice", "dal", "biryani", "banana", "pizza"]

for food in test_foods:
    result = get_nutrition(food)
    if result:
        print(f"✅ {food} → {result['food']} | {result['calories']} kcal | {result['source']}")
    else:
        print(f"❌ {food} → not found")
