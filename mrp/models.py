from django.db import models, transaction
from django.utils import timezone
from decimal import Decimal


class Material(models.Model):
    UNIT_CHOICES = [
        ("pcs", "pcs"),
        ("set", "set"),
        ("meter", "meter"),
        ("kg", "kg"),
        ("roll", "roll"),
    ]

    sku = models.CharField("Kode bahan", max_length=30, unique=True)
    name = models.CharField("Nama bahan", max_length=120)
    unit = models.CharField("Satuan", max_length=10, choices=UNIT_CHOICES, default="pcs")
    stock_on_hand = models.DecimalField("Stok tersedia", max_digits=12, decimal_places=2, default=0)
    minimum_stock = models.DecimalField("Stok minimum", max_digits=12, decimal_places=2, default=0)
    unit_price = models.DecimalField("Harga satuan", max_digits=14, decimal_places=2, default=0)
    supplier = models.CharField("Pemasok", max_length=120, blank=True)
    warehouse = models.CharField("Gudang", max_length=120, blank=True, default="Gudang utama")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Bahan baku"
        verbose_name_plural = "Bahan baku"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(stock_on_hand__gte=0),
                name="material_stock_must_be_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(minimum_stock__gte=0),
                name="material_minimum_stock_must_be_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=0),
                name="material_unit_price_nonnegative",
            ),
        ]

    def __str__(self):
        return f"{self.sku} - {self.name}"

    @property
    def is_low_stock(self):
        return self.stock_on_hand < self.minimum_stock

    @property
    def stock_status(self):
        return get_stock_status(self.stock_on_hand, self.minimum_stock)


class StockTransaction(models.Model):
    class TransactionType(models.TextChoices):
        RECEIPT = "receipt", "Barang datang"
        STOCKTAKE = "stocktake", "Stok opname"
        PRODUCTION_ISSUE = "production_issue", "Pemakaian produksi"
        PRODUCTION_OUTPUT = "production_output", "Hasil produksi"
        PURCHASE_RECEIPT = "purchase_receipt", "Penerimaan PO"
        SHIPMENT = "shipment", "Pengiriman penjualan"

    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stock_transactions",
        verbose_name="Bahan baku",
    )
    product = models.ForeignKey(
        "Product",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stock_transactions",
        verbose_name="Produk jadi",
    )
    transaction_type = models.CharField(
        "Jenis transaksi",
        max_length=24,
        choices=TransactionType.choices,
    )
    quantity = models.DecimalField(
        "Jumlah diterima / stok fisik",
        max_digits=12,
        decimal_places=2,
    )
    stock_before = models.DecimalField("Stok sebelum", max_digits=12, decimal_places=2)
    stock_after = models.DecimalField("Stok sesudah", max_digits=12, decimal_places=2)
    supplier = models.CharField("Pemasok", max_length=120, blank=True)
    reference = models.CharField("Nomor dokumen", max_length=80, blank=True)
    notes = models.TextField("Catatan", blank=True)
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_transactions",
    )
    created_at = models.DateTimeField("Waktu transaksi", auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(transaction_type="stocktake", quantity__gte=0)
                    | (
                        ~models.Q(transaction_type="stocktake")
                        & models.Q(quantity__gt=0)
                    )
                ),
                name="stock_tx_quantity_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(stock_before__gte=0) & models.Q(stock_after__gte=0),
                name="stock_transaction_balances_must_be_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(material__isnull=False, product__isnull=True)
                    | models.Q(material__isnull=True, product__isnull=False)
                ),
                name="stock_tx_one_inventory_target",
            ),
        ]
        verbose_name = "Transaksi stok"
        verbose_name_plural = "Transaksi stok"

    def __str__(self):
        inventory_item = self.material or self.product
        return f"{self.get_transaction_type_display()} - {inventory_item.name}"


class Product(models.Model):
    sku = models.CharField("Kode produk", max_length=30, unique=True)
    name = models.CharField("Nama produk", max_length=120)
    size = models.CharField("Ukuran", max_length=80, blank=True)
    stock_on_hand = models.PositiveIntegerField("Stok produk", default=0)
    minimum_stock = models.PositiveIntegerField("Stok minimum", default=0)
    sale_price = models.DecimalField("Harga jual", max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Produk"
        verbose_name_plural = "Produk"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(sale_price__gte=0),
                name="product_sale_price_nonnegative",
            ),
        ]

    def __str__(self):
        return f"{self.sku} - {self.name}"

    @property
    def stock_status(self):
        return get_stock_status(self.stock_on_hand, self.minimum_stock)

    @property
    def production_capacity(self):
        capacities = [
            int(item.material.stock_on_hand // item.quantity)
            for item in self.bom_items.select_related("material")
            if item.quantity > 0
        ]
        return min(capacities) if capacities else 0


class DemandHistory(models.Model):
    period_number = models.PositiveIntegerField("Periode")
    company_units = models.PositiveIntegerField("Volume perusahaan (unit)")
    competitor_units = models.PositiveIntegerField("Volume pesaing (unit)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["period_number"]
        constraints = [
            models.UniqueConstraint(fields=["period_number"], name="unique_demand_period"),
            models.CheckConstraint(
                condition=models.Q(period_number__gt=0),
                name="demand_period_must_be_positive",
            ),
        ]
        verbose_name = "Data historis volume"
        verbose_name_plural = "Data historis volume"

    def __str__(self):
        return f"Periode {self.period_number}: {self.company_units} unit"


class BOMItem(models.Model):
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="bom_items",
        verbose_name="Produk",
    )
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name="bom_items",
        verbose_name="Bahan baku",
    )
    quantity = models.DecimalField(
        "Kebutuhan per produk",
        max_digits=12,
        decimal_places=3,
    )

    class Meta:
        ordering = ["product__name", "material__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "material"],
                name="unique_material_per_product",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="bom_quantity_must_be_positive",
            ),
        ]
        verbose_name = "Komponen BOM"
        verbose_name_plural = "Bill of Materials"

    def __str__(self):
        return f"{self.product}: {self.material} x {self.quantity}"


class ProductionOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PLANNED = "planned", "Direncanakan"
        RELEASED = "released", "Dirilis"
        RUNNING = "running", "Berjalan"
        COMPLETED = "completed", "Selesai"
        CANCELLED = "cancelled", "Dibatalkan"

    code = models.CharField("Nomor perintah", max_length=24, unique=True, blank=True)
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="production_orders",
        verbose_name="Produk",
    )
    quantity = models.PositiveIntegerField("Jumlah produksi")
    due_date = models.DateField("Target selesai")
    status = models.CharField(
        "Status",
        max_length=12,
        choices=Status.choices,
        default=Status.PLANNED,
    )
    notes = models.TextField("Catatan", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField("Mulai produksi", null=True, blank=True)
    completed_at = models.DateTimeField("Produksi selesai", null=True, blank=True)

    class Meta:
        ordering = ["due_date", "-created_at"]
        verbose_name = "Perintah produksi"
        verbose_name_plural = "Perintah produksi"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="production_quantity_must_be_positive",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_document_code("WO")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} - {self.product.name}"


class DocumentSequence(models.Model):
    prefix = models.CharField(max_length=2)
    period = models.CharField(max_length=4)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["prefix", "period"], name="doc_period_sequence_uniq"),
        ]


class SalesOrder(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Baru"
        SHIPPED = "shipped", "Dikirim"
        PAID = "paid", "Dibayar"

    code = models.CharField("Nomor pesanan", max_length=20, unique=True, blank=True)
    customer = models.CharField("Pelanggan", max_length=120)
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="sales_orders",
        verbose_name="Produk",
    )
    quantity = models.PositiveIntegerField("Jumlah")
    unit_price = models.DecimalField("Harga jual saat pesanan", max_digits=14, decimal_places=2)
    hpp_per_unit = models.DecimalField("HPP saat pesanan", max_digits=14, decimal_places=2)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True)
    shipped_at = models.DateTimeField("Waktu pengiriman", null=True, blank=True)
    paid_at = models.DateTimeField("Waktu pembayaran", null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="sales_order_quantity_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gt=0) & models.Q(hpp_per_unit__gte=0),
                name="sales_order_prices_valid",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_document_code("SO")
        super().save(*args, **kwargs)

    @property
    def total_amount(self):
        return self.quantity * self.unit_price

    @property
    def gross_profit(self):
        return self.quantity * (self.unit_price - self.hpp_per_unit)

    def __str__(self):
        return f"{self.code} - {self.customer}"


class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        ORDERED = "ordered", "Dipesan"
        RECEIVED = "received", "Diterima"

    code = models.CharField("Nomor PO", max_length=20, unique=True, blank=True)
    material = models.ForeignKey(
        Material,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
        verbose_name="Bahan",
    )
    quantity = models.DecimalField("Jumlah", max_digits=12, decimal_places=2)
    supplier = models.CharField("Pemasok", max_length=120)
    unit_price = models.DecimalField("Harga satuan saat PO", max_digits=14, decimal_places=2)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ORDERED)
    created_at = models.DateTimeField(auto_now_add=True)
    received_at = models.DateTimeField("Waktu penerimaan", null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="purchase_order_quantity_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gt=0),
                name="purchase_order_price_positive",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = next_document_code("PO")
        super().save(*args, **kwargs)

    @property
    def total_amount(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return self.code


class CashTransaction(models.Model):
    class TransactionType(models.TextChoices):
        INCOME = "income", "Masuk"
        EXPENSE = "expense", "Keluar"

    transaction_type = models.CharField("Jenis", max_length=8, choices=TransactionType.choices)
    amount = models.DecimalField("Jumlah", max_digits=16, decimal_places=2)
    description = models.CharField("Keterangan", max_length=240)
    source_document = models.CharField("Nomor dokumen sumber", max_length=30)
    is_automatic = models.BooleanField("Dibuat otomatis", default=False)
    created_at = models.DateTimeField("Tanggal", auto_now_add=True)
    created_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_transactions",
    )

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="cash_amount_positive"),
        ]
        verbose_name = "Transaksi kas"
        verbose_name_plural = "Transaksi kas"

    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.source_document}"


class RoleProfile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MANAGER = "manager", "Manajer"
        WAREHOUSE = "warehouse", "Staf Gudang"
        PRODUCTION = "production", "Kepala Produksi"
        SALES = "sales", "Sales"
        FINANCE = "finance", "Keuangan"

    user = models.OneToOneField(
        "auth.User",
        on_delete=models.CASCADE,
        related_name="role_profile",
    )
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.MANAGER)

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"


def get_stock_status(stock, minimum):
    if stock < minimum:
        return "Di bawah minimum"
    if stock < Decimal(str(minimum)) * Decimal("1.3"):
        return "Menipis"
    return "Aman"


def next_document_code(prefix):
    period = timezone.localdate().strftime("%y%m")
    with transaction.atomic():
        sequence, _ = DocumentSequence.objects.get_or_create(
            prefix=prefix,
            period=period,
        )
        sequence = DocumentSequence.objects.select_for_update().get(pk=sequence.pk)
        sequence.last_number += 1
        sequence.save(update_fields=["last_number"])
        return f"{prefix}-{period}-{sequence.last_number:03d}"
