from django import forms
from .models import Product, Category # <--- Asegúrate de importar Category
from .models import ShippingAddress

class AddressForm(forms.ModelForm):
    class Meta:
        model = ShippingAddress
        fields = ['full_name', 'phone', 'department', 'city', 'neighborhood', 'address_line']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre quien recibe'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'type': 'tel', 'placeholder': 'Celular'}),
            'department': forms.Select(attrs={'class': 'form-select', 'id': 'dept-select'}),
            'city': forms.Select(attrs={'class': 'form-select', 'id': 'city-select'}),
            'neighborhood': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del barrio'}),
            'address_line': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Calle, Carrera, #Casa...'}),
        }



class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'category', 'product_type', 'description', 'source_file', 'image']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'product_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'source_file': forms.FileInput(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
        }
   



class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'icon']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Cumpleaños'}),
            'icon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: bi-star'}),
        }
        help_texts = {
            'icon': 'Usa nombres de iconos Bootstrap (ej: bi-heart, bi-star, bi-tag)',
        }