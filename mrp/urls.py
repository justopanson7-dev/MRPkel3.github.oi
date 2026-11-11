from django.urls import path

from . import views


urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("bahan-baku/", views.materials, name="materials"),
    path("bahan-baku/tambah/", views.material_create, name="material_create"),
    path("bahan-baku/<int:material_id>/ubah/", views.material_edit, name="material_edit"),
    path("stok/barang-datang/", views.stock_receipt, name="stock_receipt"),
    path("stok/opname/", views.stocktake, name="stocktake"),
    path("produk/", views.products, name="products"),
    path("produk/tambah/", views.product_create, name="product_create"),
    path("produk/<int:product_id>/ubah/", views.product_edit, name="product_edit"),
    path("bom/", views.bom, name="bom"),
    path("bom/<int:item_id>/ubah/", views.bom_edit, name="bom_edit"),
    path("bom/<int:item_id>/hapus/", views.bom_delete, name="bom_delete"),
    path("perintah-produksi/", views.production_orders, name="production_orders"),
    path(
        "perintah-produksi/tambah/",
        views.production_order_create,
        name="production_order_create",
    ),
    path(
        "perintah-produksi/<int:order_id>/ubah/",
        views.production_order_edit,
        name="production_order_edit",
    ),
    path(
        "perintah-produksi/<int:order_id>/mulai/",
        views.production_order_start,
        name="production_order_start",
    ),
    path(
        "perintah-produksi/<int:order_id>/selesaikan/",
        views.production_order_complete,
        name="production_order_complete",
    ),
    path("pembelian/", views.purchase_orders, name="purchase_orders"),
    path(
        "pembelian/<int:order_id>/terima/",
        views.purchase_order_receive,
        name="purchase_order_receive",
    ),
    path("penjualan/", views.sales_orders, name="sales_orders"),
    path(
        "penjualan/<int:order_id>/kirim/",
        views.sales_order_ship,
        name="sales_order_ship",
    ),
    path(
        "penjualan/<int:order_id>/bayar/",
        views.sales_order_paid,
        name="sales_order_paid",
    ),
    path("keuangan/", views.finance, name="finance"),
    path("pengguna/", views.users_and_roles, name="users_and_roles"),
    path("pengguna/<int:user_id>/peran/", views.user_role_update, name="user_role_update"),
    path("mrp/", views.mrp_report, name="mrp_report"),
    path("data-permintaan/", views.demand_history, name="demand_history"),
]
