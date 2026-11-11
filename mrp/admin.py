from django.contrib import admin

from .models import (
    BOMItem,
    CashTransaction,
    DemandHistory,
    Material,
    Product,
    ProductionOrder,
    PurchaseOrder,
    RoleProfile,
    SalesOrder,
    StockTransaction,
)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "unit", "stock_on_hand", "minimum_stock")
    search_fields = ("sku", "name")
    list_filter = ("unit",)
    readonly_fields = ("stock_on_hand",)


class BOMItemInline(admin.TabularInline):
    model = BOMItem
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("sku", "name", "stock_on_hand")
    search_fields = ("sku", "name")
    readonly_fields = ("stock_on_hand",)
    inlines = [BOMItemInline]


@admin.register(ProductionOrder)
class ProductionOrderAdmin(admin.ModelAdmin):
    list_display = ("code", "product", "quantity", "due_date", "status")
    list_filter = ("status", "due_date")
    search_fields = ("code", "product__name", "product__sku")
    readonly_fields = [field.name for field in ProductionOrder._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DemandHistory)
class DemandHistoryAdmin(admin.ModelAdmin):
    list_display = ("period_number", "company_units", "competitor_units")
    ordering = ("period_number",)


@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "transaction_type",
        "material",
        "product",
        "quantity",
        "stock_before",
        "stock_after",
        "created_by",
    )
    list_filter = ("transaction_type", "created_at")
    search_fields = ("material__sku", "material__name", "reference", "supplier")
    readonly_fields = (
        "material",
        "product",
        "transaction_type",
        "quantity",
        "stock_before",
        "stock_after",
        "supplier",
        "reference",
        "notes",
        "created_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ("code", "customer", "product", "quantity", "unit_price", "status")
    search_fields = ("code", "customer", "product__name")
    list_filter = ("status",)
    readonly_fields = [field.name for field in SalesOrder._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("code", "material", "quantity", "supplier", "unit_price", "status")
    search_fields = ("code", "material__name", "supplier")
    list_filter = ("status",)
    readonly_fields = [field.name for field in PurchaseOrder._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CashTransaction)
class CashTransactionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "source_document", "transaction_type", "amount", "is_automatic")
    list_filter = ("transaction_type", "is_automatic", "created_at")
    search_fields = ("source_document", "description")
    readonly_fields = [field.name for field in CashTransaction._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(RoleProfile)
class RoleProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role")
    list_filter = ("role",)
    search_fields = ("user__username",)
