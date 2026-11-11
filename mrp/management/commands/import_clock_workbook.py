from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from openpyxl import load_workbook

from mrp.models import BOMItem, DemandHistory, Material, Product


class Command(BaseCommand):
    help = "Impor histori volume dan BOM jam dinding dari workbook perusahaan."

    def add_arguments(self, parser):
        parser.add_argument("workbook", type=Path, help="Path file .xlsx sumber.")

    def handle(self, *args, **options):
        workbook_path = options["workbook"]
        if not workbook_path.is_file():
            raise CommandError(f"File tidak ditemukan: {workbook_path}")

        workbook = load_workbook(workbook_path, read_only=True, data_only=True)
        try:
            missing_sheets = {
                "DATA AWAL",
                "LUAS LANTAI PABRIK",
            } - set(workbook.sheetnames)
            if missing_sheets:
                raise CommandError(
                    "Sheet wajib tidak ditemukan: " + ", ".join(sorted(missing_sheets))
                )

            demand_rows = self._read_demand_rows(workbook["DATA AWAL"])
            bom_rows = self._read_bom_rows(workbook["LUAS LANTAI PABRIK"])
        finally:
            workbook.close()

        if not demand_rows:
            raise CommandError("Tidak ada data volume valid di sheet DATA AWAL.")
        if not bom_rows:
            raise CommandError("Tidak ada komponen BOM valid di sheet LUAS LANTAI PABRIK.")

        with transaction.atomic():
            product, product_created = Product.objects.get_or_create(
                sku="JD",
                defaults={"name": "Jam Dinding"},
            )
            materials_created = 0
            bom_created = 0
            for sku, name, quantity in bom_rows:
                material, created = Material.objects.get_or_create(
                    sku=sku,
                    defaults={
                        "name": name,
                        "unit": "pcs",
                        "stock_on_hand": 0,
                        "minimum_stock": 0,
                    },
                )
                materials_created += created
                _, created = BOMItem.objects.get_or_create(
                    product=product,
                    material=material,
                    defaults={"quantity": quantity},
                )
                bom_created += created

            created_periods = 0
            updated_periods = 0
            for period_number, company_units, competitor_units in demand_rows:
                _, created = DemandHistory.objects.update_or_create(
                    period_number=period_number,
                    defaults={
                        "company_units": company_units,
                        "competitor_units": competitor_units,
                    },
                )
                if created:
                    created_periods += 1
                else:
                    updated_periods += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Impor selesai: produk {'dibuat' if product_created else 'sudah ada'}, "
                f"{materials_created} bahan baru, {bom_created} komponen BOM baru, "
                f"{created_periods} periode baru, {updated_periods} periode diperbarui."
            )
        )
        self.stdout.write(
            "Stok bahan awal diset 0 karena workbook tidak menyediakan jumlah stok gudang."
        )

    @staticmethod
    def _read_demand_rows(sheet):
        rows = []
        for period, company_units, competitor_units in sheet.iter_rows(
            min_row=4,
            min_col=2,
            max_col=4,
            values_only=True,
        ):
            if period is None and company_units is None and competitor_units is None:
                continue
            if not all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for value in (period, company_units, competitor_units)
            ):
                raise CommandError(
                    "DATA AWAL harus berisi periode dan volume unit berupa bilangan bulat "
                    "nonnegatif pada kolom B-D, mulai baris 4."
                )
            rows.append((period, company_units, competitor_units))
        return rows

    @staticmethod
    def _read_bom_rows(sheet):
        rows = []
        for row in sheet.iter_rows(
            min_row=7,
            min_col=2,
            max_col=13,
            values_only=True,
        ):
            code, name = row[0], row[1]
            quantity = row[-1]
            if not code or not name:
                continue
            if not isinstance(quantity, (int, float)) or quantity <= 0:
                raise CommandError(
                    f"Jumlah kebutuhan BOM tidak valid untuk {code}: {quantity!r}"
                )
            rows.append((str(code).strip(), str(name).strip(), quantity))
        return rows
