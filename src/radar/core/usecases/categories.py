from __future__ import annotations

from radar.core.models import MessageCategory

DERIVED_INPUT_CATEGORIES: list[MessageCategory] = ["research", "recommendation", "industry"]
EXCLUDED_DERIVED_INPUT_CATEGORIES: set[MessageCategory] = {"event"}


def normalize_derived_input_categories(
    categories: list[MessageCategory] | None,
    *,
    category: MessageCategory | None = None,
) -> list[MessageCategory]:
    values = list(categories or [])
    if category:
        values.append(category)
    if not values:
        values = DERIVED_INPUT_CATEGORIES
    return [item for item in dict.fromkeys(values) if item not in EXCLUDED_DERIVED_INPUT_CATEGORIES]
