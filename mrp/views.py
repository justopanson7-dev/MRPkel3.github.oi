from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db.models import Count, F
from django.shortcuts import get_object_or_404, redirect, render

from .access import can_access, can_pay_sales, module_required, payment_required, role_for_user
from .business_services import (
    BusinessRuleError,
    calculate_unit_hpp,
    complete_production,
    create_manual_cash_transaction,
    create_purchase_order,
    create_sales_order,
    mark_sales_order_paid,
    purchase_suggestions,
    receive_purchase_order,
    ship_sales_order,
    start_production,
)
from .forms import (
    BOMItemForm,
    CashTransactionForm,
    CreateUserForm,
    MaterialForm,
    PurchaseOrderForm,
    ProductForm,
    ProductionOrderForm,
    RoleAssignmentForm,
    SalesOrderForm,
    StocktakeForm,
)
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
from .services import ACTIVE_STATUSES, calculate_material_requirements
from .stock_services import record_stocktake


@module_required("dashboard")
def dashboard(request):
    context = {
        "material_count": Material.objects.count(),
        "product_count": Product.objects.count(),
        "active_orders": ProductionOrder.objects.filter(status__in=ACTIVE_STATUSES).count(),
        "demand_periods": DemandHistory.objects.count(),
        "company_units_total": sum(
            DemandHistory.objects.values_list("company_units", flat=True)
        ),
        "low_stock_materials": [
            material
            for material in Material.objects.all()
            if material.stock_status != "Aman"
        ][:5],
        "upcoming_orders": ProductionOrder.objects.exclude(
            status__in=[ProductionOrder.Status.COMPLETED, ProductionOrder.Status.CANCELLED]
        ).select_related("product")[:6],
        "bom_count": BOMItem.objects.values("product_id").distinct().count(),
        "can_view_production": can_access(request.user, "production"),
        "can_view_history": can_access(request.user, "history"),
        "can_view_sales": can_access(request.user, "sales"),
        "can_view_purchasing": can_access(request.user, "purchasing"),
        "can_view_finance": can_access(request.user, "finance"),
        "can_change_production": can_access(request.user, "production", "change"),
    }
    return render(request, "mrp/dashboard.html", context)


@module_required("inventory")
def materials(request):
    context = {
        "materials": Material.objects.all(),
        "products": Product.objects.all(),
        "total_products": Product.objects.count(),
        "recent_transactions": StockTransaction.objects.select_related(
            "material", "product", "created_by"
        )[:10],
        "total_materials": Material.objects.count(),
        "low_stock_count": sum(
            material.stock_status != "Aman"
            for material in Material.objects.all()
        ),
    }
    return render(request, "mrp/materials.html", context)


@module_required("purchasing", "change")
def stock_receipt(request):
    messages.info(request, "Barang datang dicatat dengan menerima PO agar stok dan kas tercatat bersama.")
    return redirect("purchase_orders")


@module_required("inventory", "change")
def stocktake(request):
    form = StocktakeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        transaction_record = record_stocktake(
            material_id=form.cleaned_data["material"].pk,
            actual_stock=form.cleaned_data["actual_stock"],
            reference=form.cleaned_data["reference"],
            notes=form.cleaned_data["notes"],
            user=request.user,
        )
        messages.success(
            request,
            f"Stok opname {transaction_record.material.name} tersimpan: "
            f"{transaction_record.stock_before} → {transaction_record.stock_after} "
            f"{transaction_record.material.unit}.",
        )
        return redirect("materials")
    return render(
        request,
        "mrp/stock_form.html",
        {"form": form, "title": "Catat stok opname", "transaction_kind": "stocktake"},
    )


@module_required("inventory", "change")
def material_create(request):
    form = MaterialForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Bahan baku berhasil ditambahkan.")
        return redirect("materials")
    return render(request, "mrp/form.html", {"form": form, "title": "Tambah bahan baku"})


@module_required("inventory", "change")
def material_edit(request, material_id):
    material = get_object_or_404(Material, pk=material_id)
    form = MaterialForm(request.POST or None, instance=material)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request,
            "Data bahan baku berhasil diperbarui. Saldo stok hanya berubah melalui transaksi gudang.",
        )
        return redirect("materials")
    return render(request, "mrp/form.html", {"form": form, "title": "Ubah bahan baku"})


@module_required("production")
def products(request):
    product_list = Product.objects.annotate(component_count=Count("bom_items"))
    for product in product_list:
        product.unit_hpp = calculate_unit_hpp(product)
        product.margin = (
            (product.sale_price - product.unit_hpp) / product.sale_price
            if product.sale_price > 0
            else None
        )
    return render(request, "mrp/products.html", {"products": product_list})


@module_required("production", "change")
def product_create(request):
    form = ProductForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Produk berhasil ditambahkan.")
        return redirect("products")
    return render(request, "mrp/form.html", {"form": form, "title": "Tambah produk"})


@module_required("production", "change")
def product_edit(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    form = ProductForm(request.POST or None, instance=product)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Data produk berhasil diperbarui.")
        return redirect("products")
    return render(request, "mrp/form.html", {"form": form, "title": "Ubah produk"})


@module_required("production")
def bom(request):
    if request.method == "POST" and not can_access(request.user, "production", "change"):
        raise PermissionDenied
    form = BOMItemForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        messages.success(request, f"Komponen BOM untuk {item.product.name} berhasil disimpan.")
        return redirect("bom")
    context = {
        "form": form if can_access(request.user, "production", "change") else None,
        "bom_items": BOMItem.objects.select_related("product", "material"),
    }
    return render(request, "mrp/bom.html", context)


@module_required("production", "change")
def bom_edit(request, item_id):
    item = get_object_or_404(BOMItem, pk=item_id)
    form = BOMItemForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Komponen BOM berhasil diperbarui.")
        return redirect("bom")
    return render(request, "mrp/form.html", {"form": form, "title": "Ubah komponen BOM"})


@module_required("production", "change")
def bom_delete(request, item_id):
    item = get_object_or_404(BOMItem, pk=item_id)
    if request.method == "POST":
        item.delete()
        messages.success(request, "Komponen BOM berhasil dihapus.")
    return redirect("bom")


@module_required("production")
def production_orders(request):
    return render(
        request,
        "mrp/orders.html",
        {
            "orders": ProductionOrder.objects.select_related("product"),
            "can_change_production": can_access(request.user, "production", "change"),
        },
    )


@module_required("production", "change")
def production_order_create(request):
    form = ProductionOrderForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        order = form.save()
        messages.success(request, f"Perintah produksi {order.code} berhasil dibuat.")
        return redirect("production_orders")
    return render(
        request,
        "mrp/form.html",
        {"form": form, "title": "Buat perintah produksi"},
    )


@module_required("production", "change")
def production_order_edit(request, order_id):
    order = get_object_or_404(ProductionOrder, pk=order_id)
    if order.status != ProductionOrder.Status.PLANNED:
        messages.error(request, "Perintah hanya dapat diubah saat berstatus Direncanakan.")
        return redirect("production_orders")
    form = ProductionOrderForm(request.POST or None, instance=order)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Perintah produksi {order.code} berhasil diperbarui.")
        return redirect("production_orders")
    return render(
        request,
        "mrp/form.html",
        {"form": form, "title": f"Ubah perintah {order.code}"},
    )


@module_required("production")
def mrp_report(request):
    return render(
        request,
        "mrp/report.html",
        {
            "requirements": calculate_material_requirements(),
            "orders_without_bom": ProductionOrder.objects.filter(
                status__in=ACTIVE_STATUSES,
                product__bom_items__isnull=True,
            ).select_related("product"),
        },
    )


@module_required("history")
def demand_history(request):
    records = list(DemandHistory.objects.all())
    max_units = max(
        (max(row.company_units, row.competitor_units) for row in records),
        default=1,
    )
    for row in records:
        row.company_height = max(3, round(row.company_units / max_units * 100))
        row.competitor_height = max(3, round(row.competitor_units / max_units * 100))

    return render(
        request,
        "mrp/demand_history.html",
        {
            "records": records,
            "company_total": sum(row.company_units for row in records),
            "competitor_total": sum(row.competitor_units for row in records),
        },
    )


@module_required("production", "change")
def production_order_start(request, order_id):
    if request.method != "POST":
        raise PermissionDenied
    try:
        order = start_production(order_id=order_id, user=request.user)
    except BusinessRuleError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Produksi {order.code} dimulai; stok bahan telah dipotong.")
    return redirect("production_orders")


@module_required("production", "change")
def production_order_complete(request, order_id):
    if request.method != "POST":
        raise PermissionDenied
    try:
        order = complete_production(order_id=order_id, user=request.user)
    except BusinessRuleError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Produksi {order.code} selesai; stok produk jadi bertambah.")
    return redirect("production_orders")


@module_required("purchasing")
def purchase_orders(request):
    if request.method == "POST":
        if not can_access(request.user, "purchasing", "change"):
            raise PermissionDenied
        form = PurchaseOrderForm(request.POST)
        if form.is_valid():
            try:
                order = create_purchase_order(
                    material_id=form.cleaned_data["material"].pk,
                    quantity=form.cleaned_data["quantity"],
                )
            except BusinessRuleError as error:
                form.add_error(None, str(error))
            else:
                messages.success(request, f"PO {order.code} berhasil dibuat.")
                return redirect("purchase_orders")
    else:
        initial = {}
        material_id = request.GET.get("material")
        quantity = request.GET.get("quantity")
        if material_id:
            initial["material"] = material_id
        if quantity:
            initial["quantity"] = quantity
        form = PurchaseOrderForm(initial=initial)
    return render(
        request,
        "mrp/purchases.html",
        {
            "orders": PurchaseOrder.objects.select_related("material"),
            "suggestions": purchase_suggestions(),
            "form": form if can_access(request.user, "purchasing", "change") else None,
            "can_change_purchasing": can_access(request.user, "purchasing", "change"),
        },
    )


@module_required("purchasing", "change")
def purchase_order_receive(request, order_id):
    if request.method != "POST":
        raise PermissionDenied
    try:
        order = receive_purchase_order(order_id=order_id, user=request.user)
    except BusinessRuleError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"PO {order.code} diterima; stok dan kas keluar telah dicatat.")
    return redirect("purchase_orders")


@module_required("sales")
def sales_orders(request):
    if request.method == "POST":
        if not can_access(request.user, "sales", "change"):
            raise PermissionDenied
        form = SalesOrderForm(request.POST)
        if form.is_valid():
            try:
                order = create_sales_order(
                    customer=form.cleaned_data["customer"],
                    product_id=form.cleaned_data["product"].pk,
                    quantity=form.cleaned_data["quantity"],
                )
            except BusinessRuleError as error:
                form.add_error(None, str(error))
            else:
                messages.success(request, f"Pesanan {order.code} berhasil dibuat.")
                return redirect("sales_orders")
    else:
        form = SalesOrderForm()
    return render(
        request,
        "mrp/sales.html",
        {
            "orders": SalesOrder.objects.select_related("product"),
            "form": form if can_access(request.user, "sales", "change") else None,
            "can_change_sales": can_access(request.user, "sales", "change"),
            "can_pay_sales": can_pay_sales(request.user),
        },
    )


@module_required("sales", "change")
def sales_order_ship(request, order_id):
    if request.method != "POST":
        raise PermissionDenied
    try:
        order = ship_sales_order(order_id=order_id, user=request.user)
    except BusinessRuleError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Pesanan {order.code} dikirim; stok produk berkurang dan piutang tercatat.")
    return redirect("sales_orders")


@payment_required
def sales_order_paid(request, order_id):
    if request.method != "POST":
        raise PermissionDenied
    try:
        order = mark_sales_order_paid(order_id=order_id, user=request.user)
    except BusinessRuleError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, f"Pembayaran {order.code} tercatat sebagai kas masuk.")
    return redirect("sales_orders")


@module_required("finance")
def finance(request):
    if request.method == "POST":
        if not can_access(request.user, "finance", "change"):
            raise PermissionDenied
        form = CashTransactionForm(request.POST)
        if form.is_valid():
            try:
                transaction_record = create_manual_cash_transaction(
                    transaction_type=form.cleaned_data["transaction_type"],
                    amount=form.cleaned_data["amount"],
                    description=form.cleaned_data["description"],
                    source_document=form.cleaned_data["source_document"],
                    user=request.user,
                )
            except BusinessRuleError as error:
                form.add_error(None, str(error))
            else:
                messages.success(
                    request,
                    f"Transaksi kas untuk {transaction_record.source_document} dicatat.",
                )
                return redirect("finance")
    else:
        form = CashTransactionForm()

    recognized_orders = SalesOrder.objects.filter(
        status__in=[SalesOrder.Status.SHIPPED, SalesOrder.Status.PAID]
    )
    cash_income = sum(
        CashTransaction.objects.filter(
            transaction_type=CashTransaction.TransactionType.INCOME
        ).values_list("amount", flat=True),
        0,
    )
    cash_expense = sum(
        CashTransaction.objects.filter(
            transaction_type=CashTransaction.TransactionType.EXPENSE
        ).values_list("amount", flat=True),
        0,
    )
    return render(
        request,
        "mrp/finance.html",
        {
            "revenue": sum((order.total_amount for order in recognized_orders), 0),
            "receivables": sum(
                (order.total_amount for order in recognized_orders.filter(status=SalesOrder.Status.SHIPPED)),
                0,
            ),
            "purchase_commitments": sum(
                (
                    order.total_amount
                    for order in PurchaseOrder.objects.filter(status=PurchaseOrder.Status.ORDERED)
                ),
                0,
            ),
            "gross_profit": sum((order.gross_profit for order in recognized_orders), 0),
            "cash_income": cash_income,
            "cash_expense": cash_expense,
            "net_cash": cash_income - cash_expense,
            "cash_transactions": CashTransaction.objects.select_related("created_by"),
            "form": form if can_access(request.user, "finance", "change") else None,
        },
    )


@module_required("users", "change")
def users_and_roles(request):
    if request.method == "POST":
        form = CreateUserForm(request.POST)
        if form.is_valid():
            user = form.save()
            RoleProfile.objects.create(user=user, role=form.cleaned_data["role"])
            messages.success(request, f"Akun {user.username} berhasil dibuat.")
            return redirect("users_and_roles")
    else:
        form = CreateUserForm()
    profiles = RoleProfile.objects.select_related("user").order_by("user__username")
    return render(
        request,
        "mrp/users.html",
        {
            "form": form,
            "profiles": profiles,
            "role_choices": RoleProfile.Role.choices,
        },
    )


@module_required("users", "change")
def user_role_update(request, user_id):
    if request.method != "POST":
        raise PermissionDenied
    user = get_object_or_404(User, pk=user_id, is_superuser=False)
    profile, _ = RoleProfile.objects.get_or_create(user=user)
    form = RoleAssignmentForm(request.POST, instance=profile)
    if form.is_valid():
        form.save()
        messages.success(request, f"Peran {user.username} berhasil diperbarui.")
    else:
        messages.error(request, "Peran tidak valid.")
    return redirect("users_and_roles")
