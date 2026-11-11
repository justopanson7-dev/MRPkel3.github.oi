from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from openpyxl import Workbook

from .access import can_access
from .business_services import (
    BusinessRuleError,
    calculate_unit_hpp,
    complete_production,
    create_purchase_order,
    create_sales_order,
    mark_sales_order_paid,
    purchase_suggestions,
    receive_purchase_order,
    ship_sales_order,
    start_production,
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
from .services import calculate_material_requirements


class MRPWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="operator", password="secure-test-pass")
        RoleProfile.objects.create(user=self.user, role=RoleProfile.Role.ADMIN)
        self.client.force_login(self.user)
        self.material = Material.objects.create(
            sku="MAT-001",
            name="Mesin jam",
            unit="pcs",
            stock_on_hand=Decimal("10"),
            minimum_stock=Decimal("2"),
            unit_price=Decimal("4"),
            supplier="Pemasok A",
            warehouse="Gudang 1",
        )
        self.product = Product.objects.create(
            sku="CLK-001",
            name="Jam Dinding Minimalis",
            sale_price=Decimal("50000"),
            minimum_stock=2,
        )
        BOMItem.objects.create(
            product=self.product,
            material=self.material,
            quantity=Decimal("2"),
        )

    def test_dashboard_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('dashboard')}")

    def test_mrp_reports_net_material_shortage(self):
        ProductionOrder.objects.create(
            product=self.product,
            quantity=8,
            due_date=date(2026, 12, 1),
            status=ProductionOrder.Status.PLANNED,
        )

        row = calculate_material_requirements()[0]

        self.assertEqual(row["required"], Decimal("16"))
        self.assertEqual(row["available"], Decimal("10"))
        self.assertEqual(row["shortage"], Decimal("6"))
        self.assertTrue(row["is_short"])

    def test_mrp_page_is_available(self):
        response = self.client.get(reverse("mrp_report"))
        self.assertEqual(response.status_code, 200)

    def test_erp_module_pages_render_for_admin(self):
        for route_name in (
            "dashboard",
            "materials",
            "products",
            "bom",
            "production_orders",
            "purchase_orders",
            "sales_orders",
            "finance",
            "users_and_roles",
        ):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)

    def test_legacy_direct_receipt_redirects_to_purchase_workflow(self):
        response = self.client.post(
            reverse("stock_receipt"),
            {"material": self.material.pk, "quantity": "5.50"},
        )

        self.assertRedirects(response, reverse("purchase_orders"))
        self.material.refresh_from_db()
        self.assertEqual(self.material.stock_on_hand, Decimal("10"))
        self.assertFalse(StockTransaction.objects.exists())

    def test_stocktake_sets_physical_stock_and_allows_zero(self):
        response = self.client.post(
            reverse("stocktake"),
            {
                "material": self.material.pk,
                "actual_stock": "0",
                "reference": "SO-001",
                "notes": "Hasil hitung fisik",
            },
        )

        self.assertRedirects(response, reverse("materials"))
        self.material.refresh_from_db()
        transaction_record = StockTransaction.objects.get()
        self.assertEqual(self.material.stock_on_hand, Decimal("0"))
        self.assertEqual(transaction_record.stock_before, Decimal("10"))
        self.assertEqual(transaction_record.stock_after, Decimal("0"))
        self.assertEqual(transaction_record.quantity, Decimal("0"))

    def test_stock_transaction_pages_require_login(self):
        self.client.logout()

        for route_name in ("stocktake",):
            response = self.client.get(reverse(route_name))
            self.assertRedirects(
                response,
                f"{reverse('login')}?next={reverse(route_name)}",
            )

    def test_inventory_page_shows_current_stock_and_transaction_history(self):
        self.client.post(
            reverse("stocktake"),
            {
                "material": self.material.pk,
                "actual_stock": "13",
                "reference": "SO-100",
            },
        )

        response = self.client.get(reverse("materials"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "13")
        self.assertContains(response, "SO-100")
        self.assertContains(response, "Transaksi terbaru")

    def test_invalid_stock_transactions_do_not_change_stock(self):
        response = self.client.post(
            reverse("stocktake"),
            {"material": self.material.pk, "actual_stock": "-1"},
        )

        self.assertEqual(response.status_code, 200)
        self.material.refresh_from_db()
        self.assertEqual(self.material.stock_on_hand, Decimal("10"))
        self.assertFalse(StockTransaction.objects.exists())

    def test_demand_history_page_shows_period_data(self):
        DemandHistory.objects.create(
            period_number=1,
            company_units=120,
            competitor_units=90,
        )

        response = self.client.get(reverse("demand_history"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Histori volume jam dinding")
        self.assertContains(response, "120")

    def test_workbook_import_is_repeatable(self):
        with TemporaryDirectory() as directory:
            workbook_path = Path(directory) / "clock-data.xlsx"
            workbook = Workbook()
            demand_sheet = workbook.active
            demand_sheet.title = "DATA AWAL"
            demand_sheet["B4"] = 1
            demand_sheet["C4"] = 120
            demand_sheet["D4"] = 90
            floor_sheet = workbook.create_sheet("LUAS LANTAI PABRIK")
            floor_sheet["B7"] = "A-1"
            floor_sheet["C7"] = "Body depan jam"
            floor_sheet["M7"] = 1
            workbook.save(workbook_path)

            call_command("import_clock_workbook", workbook_path, stdout=StringIO())
            call_command("import_clock_workbook", workbook_path, stdout=StringIO())

        self.assertEqual(DemandHistory.objects.count(), 1)
        self.assertEqual(DemandHistory.objects.get().company_units, 120)
        self.assertEqual(Material.objects.filter(sku="A-1").count(), 1)
        self.assertEqual(
            BOMItem.objects.filter(product__sku="JD", material__sku="A-1").count(),
            1,
        )

    def test_hpp_stock_status_and_production_capacity(self):
        self.assertEqual(calculate_unit_hpp(self.product), Decimal("20008.000"))
        self.assertEqual(self.product.production_capacity, 5)
        self.assertEqual(self.material.stock_status, "Aman")

        self.material.stock_on_hand = Decimal("2.5")
        self.material.save(update_fields=["stock_on_hand"])
        self.assertEqual(self.material.stock_status, "Menipis")
        self.material.stock_on_hand = Decimal("1.99")
        self.material.save(update_fields=["stock_on_hand"])
        self.assertEqual(self.material.stock_status, "Di bawah minimum")

    def test_production_shortage_does_not_partially_consume_materials(self):
        second_material = Material.objects.create(
            sku="MAT-002",
            name="Jarum jam",
            stock_on_hand=Decimal("1"),
            minimum_stock=Decimal("0"),
        )
        BOMItem.objects.create(
            product=self.product,
            material=second_material,
            quantity=Decimal("1"),
        )
        order = ProductionOrder.objects.create(
            product=self.product,
            quantity=2,
            due_date=date(2026, 12, 1),
            status=ProductionOrder.Status.PLANNED,
        )

        with self.assertRaisesRegex(BusinessRuleError, "Jarum jam kurang 1.000 pcs"):
            start_production(order_id=order.pk, user=self.user)

        self.material.refresh_from_db()
        second_material.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.material.stock_on_hand, Decimal("10"))
        self.assertEqual(second_material.stock_on_hand, Decimal("1"))
        self.assertEqual(order.status, ProductionOrder.Status.PLANNED)
        self.assertFalse(StockTransaction.objects.exists())

    def test_production_consumes_materials_then_adds_finished_goods_once(self):
        order = ProductionOrder.objects.create(
            product=self.product,
            quantity=3,
            due_date=date(2026, 12, 1),
            status=ProductionOrder.Status.PLANNED,
        )

        start_production(order_id=order.pk, user=self.user)
        self.material.refresh_from_db()
        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.material.stock_on_hand, Decimal("4"))
        self.assertEqual(self.product.stock_on_hand, 0)
        self.assertEqual(order.status, ProductionOrder.Status.RUNNING)

        complete_production(order_id=order.pk, user=self.user)
        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.stock_on_hand, 3)
        self.assertEqual(order.status, ProductionOrder.Status.COMPLETED)
        with self.assertRaises(BusinessRuleError):
            complete_production(order_id=order.pk, user=self.user)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_on_hand, 3)

    def test_sales_order_locks_price_and_hpp_then_ships_and_pays_once(self):
        order = create_sales_order(
            customer="Pelanggan A",
            product_id=self.product.pk,
            quantity=2,
        )
        self.product.sale_price = Decimal("70000")
        self.product.save(update_fields=["sale_price"])
        self.assertEqual(order.unit_price, Decimal("50000"))
        self.assertEqual(order.hpp_per_unit, Decimal("20008.000"))

        with self.assertRaisesRegex(BusinessRuleError, "kurang 2 unit"):
            ship_sales_order(order_id=order.pk, user=self.user)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_on_hand, 0)

        self.product.stock_on_hand = 2
        self.product.save(update_fields=["stock_on_hand"])
        ship_sales_order(order_id=order.pk, user=self.user)
        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.stock_on_hand, 0)
        self.assertEqual(order.status, SalesOrder.Status.SHIPPED)
        self.assertEqual(order.total_amount, Decimal("100000"))

        mark_sales_order_paid(order_id=order.pk, user=self.user)
        self.assertEqual(CashTransaction.objects.filter(source_document=order.code).count(), 1)
        with self.assertRaises(BusinessRuleError):
            mark_sales_order_paid(order_id=order.pk, user=self.user)
        self.assertEqual(CashTransaction.objects.filter(source_document=order.code).count(), 1)

    def test_purchase_receipt_updates_stock_cash_and_rejects_duplicate(self):
        order = create_purchase_order(material_id=self.material.pk, quantity=Decimal("5"))
        self.assertEqual(order.supplier, "Pemasok A")
        self.assertEqual(order.total_amount, Decimal("20"))
        self.assertEqual(self.material.stock_on_hand, Decimal("10"))

        receive_purchase_order(order_id=order.pk, user=self.user)
        self.material.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.material.stock_on_hand, Decimal("15"))
        self.assertEqual(order.status, PurchaseOrder.Status.RECEIVED)
        self.assertEqual(CashTransaction.objects.filter(source_document=order.code).count(), 1)
        with self.assertRaises(BusinessRuleError):
            receive_purchase_order(order_id=order.pk, user=self.user)
        self.assertEqual(CashTransaction.objects.filter(source_document=order.code).count(), 1)

    def test_purchase_suggestion_uses_tens_and_skips_material_with_open_po(self):
        self.material.stock_on_hand = Decimal("1")
        self.material.minimum_stock = Decimal("10")
        self.material.save(update_fields=["stock_on_hand", "minimum_stock"])
        suggestion = purchase_suggestions()
        self.assertEqual(suggestion[0]["material"], self.material)
        self.assertEqual(suggestion[0]["quantity"], Decimal("20"))

        create_purchase_order(material_id=self.material.pk, quantity=Decimal("10"))
        self.assertFalse(purchase_suggestions())

    def test_role_permissions_match_module_write_access(self):
        self.user.role_profile.role = RoleProfile.Role.SALES
        self.user.role_profile.save(update_fields=["role"])
        self.assertTrue(can_access(self.user, "sales", "change"))
        self.assertFalse(can_access(self.user, "purchasing", "change"))
        self.assertTrue(can_access(self.user, "inventory", "view"))
        self.assertFalse(can_access(self.user, "finance", "view"))
