from django.db import transaction

from .models import Material, StockTransaction


@transaction.atomic
def record_stocktake(*, material_id, actual_stock, reference="", notes="", user=None):
    if actual_stock < 0:
        raise ValueError("Stok hasil opname tidak boleh negatif.")
    material = Material.objects.select_for_update().get(pk=material_id)
    stock_before = material.stock_on_hand
    material.stock_on_hand = actual_stock
    material.save(update_fields=["stock_on_hand"])
    return StockTransaction.objects.create(
        material=material,
        transaction_type=StockTransaction.TransactionType.STOCKTAKE,
        quantity=actual_stock,
        stock_before=stock_before,
        stock_after=actual_stock,
        reference=reference,
        notes=notes,
        created_by=user,
    )
