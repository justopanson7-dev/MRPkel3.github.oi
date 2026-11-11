import django.db.models.deletion
import uuid
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Material",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sku", models.CharField(max_length=30, unique=True, verbose_name="Kode bahan")),
                ("name", models.CharField(max_length=120, verbose_name="Nama bahan")),
                ("unit", models.CharField(choices=[("pcs", "pcs"), ("set", "set"), ("meter", "meter"), ("kg", "kg"), ("roll", "roll")], default="pcs", max_length=10, verbose_name="Satuan")),
                ("stock_on_hand", models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name="Stok tersedia")),
                ("minimum_stock", models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name="Stok minimum")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Bahan baku",
                "verbose_name_plural": "Bahan baku",
                "ordering": ["name"],
            },
        ),
        migrations.AddConstraint(
            model_name="material",
            constraint=models.CheckConstraint(condition=models.Q(("stock_on_hand__gte", 0)), name="material_stock_must_be_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="material",
            constraint=models.CheckConstraint(condition=models.Q(("minimum_stock__gte", 0)), name="material_minimum_stock_must_be_nonnegative"),
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sku", models.CharField(max_length=30, unique=True, verbose_name="Kode produk")),
                ("name", models.CharField(max_length=120, verbose_name="Nama produk")),
                ("stock_on_hand", models.PositiveIntegerField(default=0, verbose_name="Stok produk")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Produk",
                "verbose_name_plural": "Produk",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="ProductionOrder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(blank=True, max_length=24, unique=True, verbose_name="Nomor perintah")),
                ("quantity", models.PositiveIntegerField(verbose_name="Jumlah produksi")),
                ("due_date", models.DateField(verbose_name="Target selesai")),
                ("status", models.CharField(choices=[("draft", "Draft"), ("planned", "Direncanakan"), ("released", "Dirilis"), ("completed", "Selesai"), ("cancelled", "Dibatalkan")], default="planned", max_length=12, verbose_name="Status")),
                ("notes", models.TextField(blank=True, verbose_name="Catatan")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="production_orders", to="mrp.product", verbose_name="Produk")),
            ],
            options={
                "verbose_name": "Perintah produksi",
                "verbose_name_plural": "Perintah produksi",
                "ordering": ["due_date", "-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="productionorder",
            constraint=models.CheckConstraint(condition=models.Q(("quantity__gt", 0)), name="production_quantity_must_be_positive"),
        ),
        migrations.CreateModel(
            name="BOMItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.DecimalField(decimal_places=3, max_digits=12, verbose_name="Kebutuhan per produk")),
                ("material", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bom_items", to="mrp.material", verbose_name="Bahan baku")),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bom_items", to="mrp.product", verbose_name="Produk")),
            ],
            options={
                "verbose_name": "Komponen BOM",
                "verbose_name_plural": "Bill of Materials",
                "ordering": ["product__name", "material__name"],
            },
        ),
        migrations.AddConstraint(
            model_name="bomitem",
            constraint=models.UniqueConstraint(fields=("product", "material"), name="unique_material_per_product"),
        ),
        migrations.AddConstraint(
            model_name="bomitem",
            constraint=models.CheckConstraint(condition=models.Q(("quantity__gt", 0)), name="bom_quantity_must_be_positive"),
        ),
    ]
