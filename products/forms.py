from django import forms
from .models import Product, Category # <--- Asegúrate de importar Category

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