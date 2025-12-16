from django.db import models
from django.core.files.base import ContentFile
from pdf2image import convert_from_bytes
import io
import os

# --- MODELOS AUXILIARES ---
class Category(models.Model):
    name = models.CharField("Categoría", max_length=100)
    slug = models.SlugField(unique=True)
    icon = models.CharField(max_length=50, default='bi-tag', help_text="Clase de icono Bootstrap (ej: bi-star)")
    def __str__(self): return self.name

class Size(models.Model):
    name = models.CharField("Nombre Tamaño", max_length=50) # Ej: Grande
    dimensions = models.CharField("Dimensiones", max_length=50) # Ej: 19x25cm
    
    def __str__(self): return f"{self.name} ({self.dimensions})"

class Material(models.Model):
    name = models.CharField("Material", max_length=50) # Ej: Vinilo, Mailan
    is_special = models.BooleanField(default=False) # Para saber si es Mailan/Metalizado
    
    def __str__(self): return self.name

class Color(models.Model):
    name = models.CharField("Color", max_length=50) # Ej: Dorado, Rojo
    hex_code = models.CharField("Código Hex", max_length=7, default="#000000") # Para mostrar bolita de color
    
    def __str__(self): return self.name

# --- PRODUCTO PRINCIPAL ---
class Product(models.Model):
    TYPE_CHOICES = (
        ('vinilo_corte', 'Vinilo de Corte'),
        ('impreso_globo', 'Impreso para Globos'),
        ('cinta', 'Cinta Ramos'),
        ('logo', 'Stickers Logo'),
    )

    name = models.CharField("Referencia / Nombre", max_length=200)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    product_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='vinilo_corte')
    description = models.TextField(blank=True)
    
    # EL PDF ORIGINAL (Se va a AWS S3)
    source_file = models.FileField("Archivo PDF/Fuente", upload_to='source_files/', blank=True, null=True)
    
    # LA IMAGEN DEL CATÁLOGO (Se genera auto o manual)
    image = models.ImageField("Imagen Catálogo", upload_to='products_img/', blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Auto-generar imagen si suben un PDF
        if self.source_file and self.source_file.name.lower().endswith('.pdf') and not self.image:
            try:
                # Nota: pdf2image requiere poppler instalado en el sistema
                images = convert_from_bytes(self.source_file.read())
                if images:
                    # Convertimos a RGB y guardamos en memoria
                    thumb_io = io.BytesIO()
                    images[0].convert('RGB').save(thumb_io, format='JPEG', quality=85)
                    # Guardamos el archivo en el campo image
                    filename = f"{self.name}_preview.jpg"
                    self.image.save(filename, ContentFile(thumb_io.getvalue()), save=False)
            except Exception as e:
                print(f"Advertencia: No se pudo generar preview del PDF. {e}")
        
        super().save(*args, **kwargs)

    def __str__(self): return self.name

# --- VARIANTES (PRECIOS Y STOCK) ---
class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    
    # Características
    size = models.ForeignKey(Size, on_delete=models.PROTECT)
    material = models.ForeignKey(Material, on_delete=models.PROTECT)
    color = models.ForeignKey(Color, on_delete=models.PROTECT, blank=True, null=True) # Opcional para impresos
    
    price = models.DecimalField("Precio", max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=100)
    
    def __str__(self):
        return f"{self.product.name} - {self.size.name} - ${self.price}"