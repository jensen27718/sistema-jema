from django.db import models
from django.utils.text import slugify
from django.core.files.base import ContentFile
from pdf2image import convert_from_bytes
from PIL import Image  
import io
import os
from django.conf import settings
# ... (Tus modelos anteriores Product, Variant, etc) ...



class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cart', null=True, blank=True)
    # Si quisieras carrito para no logueados usaríamos sesiones, pero empecemos con usuarios
    created_at = models.DateTimeField(auto_now_add=True)

    def get_total(self):
        return sum(item.get_cost() for item in self.items.all())

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    variant = models.ForeignKey('ProductVariant', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def get_cost(self):
        return self.variant.price * self.quantity




# --- MODELOS AUXILIARES ---
class Category(models.Model):
    name = models.CharField("Categoría", max_length=100)
    slug = models.SlugField(unique=True, blank=True) # Agregamos blank=True por si acaso
    icon = models.CharField(max_length=50, default='bi-tag', help_text="Clase de icono Bootstrap (ej: bi-star)")
    # --- 2. AGREGA ESTE MÉTODO SAVE ---
    def save(self, *args, **kwargs):
        if not self.slug:  # Si no tiene slug...
            self.slug = slugify(self.name)  # ...lo crea desde el nombre (Ej: "Globos Rojos" -> "globos-rojos")
        super().save(*args, **kwargs)

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
    
    # Archivo original (Alta Calidad / Vector) -> Se va a AWS S3
    source_file = models.FileField("Archivo Fuente (PDF/PNG)", upload_to='source_files/', blank=True, null=True)
    
    # Imagen ligera para la web -> Se va a AWS S3
    image = models.ImageField("Imagen Catálogo", upload_to='products_img/', blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # SOLO actuamos si hay un archivo fuente y NO hay imagen de catálogo subida manualmente
        if self.source_file and not self.image:
            
            # Obtener extensión del archivo (.pdf, .png, .jpg)
            ext = os.path.splitext(self.source_file.name)[1].lower()
            file_name = os.path.splitext(os.path.basename(self.source_file.name))[0]

            try:
                # --- CASO 1: ES UN PDF (Tus Vinilos de Corte) ---
                if ext == '.pdf':
                    images = convert_from_bytes(self.source_file.read())
                    if images:
                        thumb_io = io.BytesIO()
                        # Convertimos a RGB y guardamos como JPEG
                        images[0].convert('RGB').save(thumb_io, format='JPEG', quality=85)
                        self.image.save(f"{file_name}_preview.jpg", ContentFile(thumb_io.getvalue()), save=False)

                # --- CASO 2: ES UNA IMAGEN (Tus Stickers Impresos PNG/JPG) ---
                elif ext in ['.png', '.jpg', '.jpeg']:
                    # Abrimos la imagen original
                    img = Image.open(self.source_file)
                    
                    # Si es PNG con transparencia (RGBA), poner fondo blanco
                    if img.mode in ('RGBA', 'LA'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[3])
                        img = background
                    else:
                        img = img.convert('RGB')

                    # Guardamos optimizada en formato WebP (Muy ligero)
                    thumb_io = io.BytesIO()
                    img.save(thumb_io, format='WEBP', quality=80)
                    
                    self.image.save(f"{file_name}_web.webp", ContentFile(thumb_io.getvalue()), save=False)

            except Exception as e:
                print(f"Error procesando archivo fuente: {e}")
        
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