"""Stable spending categories and exact-history key normalization."""

from typing import Literal, get_args

SpendingCategory = Literal[
    "unknown", "other", "milk", "cheese", "yogurt", "eggs", "butter_spreads",
    "bread_bakery", "cereals", "pasta_rice_grains", "vegetables", "fruit",
    "meat", "fish", "ready_meals", "snacks_sweets", "coffee_tea", "water",
    "soft_drinks", "alcohol", "sauces_spices", "cleaning", "household",
    "personal_care", "pet", "health", "clothing", "electronics", "hardware",
    "restaurant", "fuel", "services", "deposit",
]
CATEGORY_CODES: tuple[str, ...] = get_args(SpendingCategory)
CATEGORY_CODE_SET = frozenset(CATEGORY_CODES)

CATEGORY_DEFINITIONS = {
    "unknown": "Could not tell from the receipt",
    "other": "Known item outside the other categories",
    "milk": "Dairy milk and plant milk alternatives",
    "cheese": "Cheese",
    "yogurt": "Yogurt and quark",
    "eggs": "Eggs",
    "butter_spreads": "Butter, margarine, and spreads",
    "bread_bakery": "Bread and bakery items",
    "cereals": "Breakfast cereals and muesli",
    "pasta_rice_grains": "Pasta, rice, and grains",
    "vegetables": "Vegetables",
    "fruit": "Fruit",
    "meat": "Meat",
    "fish": "Fish and seafood",
    "ready_meals": "Prepared meals",
    "snacks_sweets": "Snacks and sweets",
    "coffee_tea": "Coffee and tea",
    "water": "Water",
    "soft_drinks": "Soft drinks and juice",
    "alcohol": "Alcoholic drinks",
    "sauces_spices": "Sauces, spices, and condiments",
    "cleaning": "Cleaning products",
    "household": "Household supplies",
    "personal_care": "Personal care and hygiene",
    "pet": "Pet products",
    "health": "Medicines and health products",
    "clothing": "Clothing",
    "electronics": "Electronics",
    "hardware": "Tools and hardware",
    "restaurant": "Restaurant food and drinks",
    "fuel": "Fuel",
    "services": "Services",
    "deposit": "Container deposit or refund",
}


def normalize_history_key(value: str) -> str:
    """Unicode-aware case folding and whitespace collapse; retain digits/punctuation."""
    return " ".join(value.split()).casefold()


def llm_category(value: object) -> str:
    """Unsupported model output has no spending authority."""
    return value if isinstance(value, str) and value in CATEGORY_CODE_SET else "unknown"
