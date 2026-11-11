from collections import defaultdict
from decimal import Decimal

from django.db.models import Prefetch

from .models import BOMItem, ProductionOrder


ACTIVE_STATUSES = [
    ProductionOrder.Status.PLANNED,
    ProductionOrder.Status.RELEASED,
]


def calculate_material_requirements():
    requirements = defaultdict(lambda: Decimal("0"))
    materials = {}
    orders = (
        ProductionOrder.objects.filter(status__in=ACTIVE_STATUSES)
        .select_related("product")
        .prefetch_related(
            Prefetch(
                "product__bom_items",
                queryset=BOMItem.objects.select_related("material"),
            )
        )
    )

    for order in orders:
        for item in order.product.bom_items.all():
            requirements[item.material_id] += item.quantity * order.quantity
            materials[item.material_id] = item.material

    rows = []
    for material_id, required in requirements.items():
        material = materials[material_id]
        shortage = max(required - material.stock_on_hand, Decimal("0"))
        rows.append(
            {
                "material": material,
                "required": required,
                "available": material.stock_on_hand,
                "shortage": shortage,
                "is_short": shortage > 0,
            }
        )
    return sorted(rows, key=lambda row: row["material"].name.lower())
