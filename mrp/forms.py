from decimal import Decimal

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import BOMItem, CashTransaction, Material, Product, ProductionOrder, RoleProfile


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class MaterialForm(StyledModelForm):
    class Meta:
        model = Material
        fields = [
            "sku",
            "name",
            "unit",
            "minimum_stock",
            "unit_price",
            "supplier",
            "warehouse",
        ]
        widgets = {
            "minimum_stock": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
            "unit_price": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
        }

    def clean_minimum_stock(self):
        value = self.cleaned_data["minimum_stock"]
        if value < 0:
            raise forms.ValidationError("Stok minimum tidak boleh bernilai negatif.")
        return value


class StocktakeForm(forms.Form):
    material = forms.ModelChoiceField(
        label="Bahan baku",
        queryset=Material.objects.order_by("name"),
    )
    actual_stock = forms.DecimalField(
        label="Jumlah stok fisik",
        min_value=Decimal("0"),
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
    )
    reference = forms.CharField(label="Nomor dokumen", max_length=80, required=False)
    notes = forms.CharField(
        label="Catatan",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class ProductForm(StyledModelForm):
    class Meta:
        model = Product
        fields = ["sku", "name", "size", "minimum_stock", "sale_price"]
        widgets = {
            "minimum_stock": forms.NumberInput(attrs={"min": "0"}),
            "sale_price": forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
        }


class BOMItemForm(StyledModelForm):
    class Meta:
        model = BOMItem
        fields = ["product", "material", "quantity"]
        widgets = {"quantity": forms.NumberInput(attrs={"min": "0.001", "step": "0.001"})}

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity <= 0:
            raise forms.ValidationError("Kebutuhan bahan harus lebih dari nol.")
        return quantity


class ProductionOrderForm(StyledModelForm):
    class Meta:
        model = ProductionOrder
        fields = ["product", "quantity", "due_date", "notes"]
        widgets = {
            "quantity": forms.NumberInput(attrs={"min": "1"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity <= 0:
            raise forms.ValidationError("Jumlah produksi harus lebih dari nol.")
        return quantity


class SalesOrderForm(forms.Form):
    customer = forms.CharField(label="Pelanggan", max_length=120)
    product = forms.ModelChoiceField(label="Produk", queryset=Product.objects.order_by("name"))
    quantity = forms.IntegerField(label="Jumlah", min_value=1)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
        self.fields["quantity"].widget.attrs.update({"min": "1", "step": "1"})


class PurchaseOrderForm(forms.Form):
    material = forms.ModelChoiceField(label="Bahan", queryset=Material.objects.order_by("name"))
    quantity = forms.DecimalField(
        label="Jumlah dipesan",
        min_value=Decimal("0.01"),
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class CashTransactionForm(forms.Form):
    transaction_type = forms.ChoiceField(
        label="Jenis transaksi",
        choices=CashTransaction.TransactionType.choices,
    )
    amount = forms.DecimalField(
        label="Jumlah (Rp)",
        min_value=Decimal("0.01"),
        max_digits=16,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
    )
    source_document = forms.CharField(label="Nomor dokumen sumber", max_length=30)
    description = forms.CharField(label="Keterangan", max_length=240)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class CreateUserForm(UserCreationForm):
    role = forms.ChoiceField(label="Peran", choices=RoleProfile.Role.choices)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "role")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"


class RoleAssignmentForm(forms.ModelForm):
    class Meta:
        model = RoleProfile
        fields = ["role"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control"
