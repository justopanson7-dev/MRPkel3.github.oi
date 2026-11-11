from decimal import Decimal, ROUND_CEILING

from django.db import transaction
from django.utils import timezone

from .models import (
    BOMItem,
    CashTransaction,
    Material,
    Product,
    ProductionOrder,
    PurchaseOrder,
    SalesOrder,
    StockTransaction,
)


ASSEMBLY_LABOR = Decimal("20000")


class BusinessRuleError(Exception):
    pass


def calculate_unit_hpp(product):
    materials_cost = sum(
        (item.material.unit_price * item.quantity for item in product.bom_items.select_related("material")),
        Decimal("0"),
    )
    return materials_cost + ASSEMBLY_LABOR


def create_sales_order(*, customer, product_id, quantity):
    product = Product.objects.get(pk=product_id)
    if quantity <= 0:
        raise BusinessRuleError("Jumlah pesanan harus lebih dari nol.")
    if product.sale_price <= 0:
        raise BusinessRuleError("Harga jual produk harus diisi lebih dari nol sebelum membuat pesanan.")
    return SalesOrder.objects.create(
        customer=customer,
        product=product,
        quantity=quantity,
        unit_price=product.sale_price,
        hpp_per_unit=calculate_unit_hpp(product),
    )


@transaction.atomic
def ship_sales_order(*, order_id, user):
    order = SalesOrder.objects.select_for_update().select_related("product").get(pk=order_id)
    if order.status != SalesOrder.Status.NEW:
        raise BusinessRuleError(f"Pesanan {order.code} tidak lagi berstatus Baru.")
    product = Product.objects.select_for_update().get(pk=order.product_id)
    if product.stock_on_hand < order.quantity:
        shortage = order.quantity - product.stock_on_hand
        raise BusinessRuleError(
            f"Stok {product.name} kurang {shortage} unit. Buat perintah produksi terlebih dahulu."
        )
    before = product.stock_on_hand
    product.stock_on_hand -= order.quantity
    product.save(update_fields=["stock_on_hand"])
    order.status = SalesOrder.Status.SHIPPED
    order.shipped_at = timezone.now()
    order.save(update_fields=["status", "shipped_at"])
    StockTransaction.objects.create(
        product=product,
        transaction_type=StockTransaction.TransactionType.SHIPMENT,
        quantity=order.quantity,
        stock_before=before,
        stock_after=product.stock_on_hand,
        reference=order.code,
        notes=f"Pengiriman ke {order.customer}",
        created_by=user,
    )
    return order


@transaction.atomic
def mark_sales_order_paid(*, order_id, user):
    order = SalesOrder.objects.select_for_update().get(pk=order_id)
    if order.status != SalesOrder.Status.SHIPPED:
        raise BusinessRuleError(f"Pesanan {order.code} harus berstatus Dikirim sebelum dibayar.")
    order.status = SalesOrder.Status.PAID
    order.paid_at = timezone.now()
    order.save(update_fields=["status", "paid_at"])
    CashTransaction.objects.create(
        transaction_type=CashTransaction.TransactionType.INCOME,
        amount=order.total_amount,
        description=f"Pembayaran {order.code} {order.customer}",
        source_document=order.code,
        is_automatic=True,
        created_by=user,
    )
    return order


@transaction.atomic
def start_production(*, order_id, user):
    order = ProductionOrder.objects.select_for_update().get(pk=order_id)
    if order.status != ProductionOrder.Status.PLANNED:
        raise BusinessRuleError(f"Perintah {order.code} harus berstatus Direncanakan untuk dimulai.")
    bom_items = list(
        BOMItem.objects.filter(product_id=order.product_id)
        .select_related("material")
        .order_by("material_id")
    )
    if not bom_items:
        raise BusinessRuleError(f"Produk {order.product} belum memiliki BOM.")
    materials = {
        material.pk: material
        for material in Material.objects.select_for_update()
        .filter(pk__in=[item.material_id for item in bom_items])
        .order_by("pk")
    }
    shortages = []
    requirements = {}
    for item in bom_items:
        material = materials[item.material_id]
        required = item.quantity * order.quantity
        requirements[material.pk] = (material, required)
        if material.stock_on_hand < required:
            shortages.append(
                f"{material.name} kurang {required - material.stock_on_hand} {material.unit}"
            )
    if shortages:
        raise BusinessRuleError("Stok bahan tidak cukup: " + "; ".join(shortages) + ".")
    for material, required in requirements.values():
        before = material.stock_on_hand
        material.stock_on_hand -= required
        material.save(update_fields=["stock_on_hand"])
        StockTransaction.objects.create(
            material=material,
            transaction_type=StockTransaction.TransactionType.PRODUCTION_ISSUE,
            quantity=required,
            stock_before=before,
            stock_after=material.stock_on_hand,
            reference=order.code,
            created_by=user,
        )
    order.status = ProductionOrder.Status.RUNNING
    order.started_at = timezone.now()
    order.save(update_fields=["status", "started_at"])
    return order


@transaction.atomic
def complete_production(*, order_id, user):
    order = ProductionOrder.objects.select_for_update().get(pk=order_id)
    if order.status != ProductionOrder.Status.RUNNING:
        raise BusinessRuleError(f"Perintah {order.code} harus berstatus Berjalan untuk diselesaikan.")
    product = Product.objects.select_for_update().get(pk=order.product_id)
    before = product.stock_on_hand
    product.stock_on_hand += order.quantity
    product.save(update_fields=["stock_on_hand"])
    order.status = ProductionOrder.Status.COMPLETED
    order.completed_at = timezone.now()
    order.save(update_fields=["status", "completed_at"])
    StockTransaction.objects.create(
        product=product,
        transaction_type=StockTransaction.TransactionType.PRODUCTION_OUTPUT,
        quantity=order.quantity,
        stock_before=before,
        stock_after=product.stock_on_hand,
        reference=order.code,
        created_by=user,
    )
    return order


@transaction.atomic
def create_purchase_order(*, material_id, quantity):
    material = Material.objects.select_for_update().get(pk=material_id)
    if quantity <= 0:
        raise BusinessRuleError("Jumlah PO harus lebih dari nol.")
    if not material.supplier.strip():
        raise BusinessRuleError(f"Isi pemasok pada data bahan {material.name} sebelum membuat PO.")
    if material.unit_price <= 0:
        raise BusinessRuleError(f"Isi harga satuan pada data bahan {material.name} sebelum membuat PO.")
    return PurchaseOrder.objects.create(
        material=material,
        quantity=quantity,
        supplier=material.supplier,
        unit_price=material.unit_price,
    )


@transaction.atomic
def receive_purchase_order(*, order_id, user):
    order = PurchaseOrder.objects.select_for_update().get(pk=order_id)
    if order.status != PurchaseOrder.Status.ORDERED:
        raise BusinessRuleError(f"PO {order.code} sudah pernah diproses atau tidak lagi Dipesan.")
    material = Material.objects.select_for_update().get(pk=order.material_id)
    before = material.stock_on_hand
    material.stock_on_hand += order.quantity
    material.save(update_fields=["stock_on_hand"])
    order.status = PurchaseOrder.Status.RECEIVED
    order.received_at = timezone.now()
    order.save(update_fields=["status", "received_at"])
    StockTransaction.objects.create(
        material=material,
        transaction_type=StockTransaction.TransactionType.PURCHASE_RECEIPT,
        quantity=order.quantity,
        stock_before=before,
        stock_after=material.stock_on_hand,
        supplier=order.supplier,
        reference=order.code,
        created_by=user,
    )
    CashTransaction.objects.create(
        transaction_type=CashTransaction.TransactionType.EXPENSE,
        amount=order.total_amount,
        description=f"Penerimaan {order.code} {order.supplier}",
        source_document=order.code,
        is_automatic=True,
        created_by=user,
    )
    return order


def purchase_suggestions():
    pending_material_ids = PurchaseOrder.objects.filter(
        status=PurchaseOrder.Status.ORDERED
    ).values_list("material_id", flat=True)
    suggestions = []
    for material in Material.objects.exclude(pk__in=pending_material_ids):
        if material.minimum_stock <= 0 or material.stock_on_hand >= material.minimum_stock:
            continue
        quantity = max(
            Decimal("10"),
            ((material.minimum_stock * 2 - material.stock_on_hand) / Decimal("10")).to_integral_value(
                rounding=ROUND_CEILING
            ) * Decimal("10"),
        )
        suggestions.append({"material": material, "quantity": quantity})
    return suggestions


def create_manual_cash_transaction(*, transaction_type, amount, description, source_document, user):
    clean_source = source_document.strip()
    clean_description = description.strip()
    if not clean_source or not clean_description:
        raise BusinessRuleError("Keterangan dan nomor dokumen sumber wajib diisi.")
    if clean_source not in clean_description:
        clean_description = f"{clean_description} {clean_source}"
    if amount <= 0:
        raise BusinessRuleError("Jumlah transaksi kas harus lebih dari nol.")
    return CashTransaction.objects.create(
        transaction_type=transaction_type,
        amount=amount,
        description=clean_description,
        source_document=clean_source,
        is_automatic=False,
        created_by=user,
    )
