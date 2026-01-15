from django.db import models
from django.utils.text import slugify
from django.core.files.base import ContentFile
# import fitz (moved inside save for robustness)
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
    slug = models.SlugField(unique=True, blank=True)
    icon = models.CharField(max_length=50, default='bi-tag', help_text="Clase de icono Bootstrap (ej: bi-star)")
    image = models.ImageField("Icono/Imagen", upload_to='categories/', blank=True, null=True, help_text="Imagen cuadrada para el menú (PNG/JPG)")
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
    categories = models.ManyToManyField(Category, related_name='products', blank=True)  # Relación M2M para múltiples categorías
    product_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='vinilo_corte')
    description = models.TextField(blank=True)

    # Archivo original (Alta Calidad / Vector) -> Se va a AWS S3
    source_file = models.FileField("Archivo Fuente (PDF/PNG)", upload_to='source_files/', blank=True, null=True)

    # Imagen ligera para la web -> Se va a AWS S3
    image = models.ImageField("Imagen Catálogo", upload_to='products_img/', blank=True, null=True)

    # Control de visibilidad en catálogo público
    is_online = models.BooleanField("Visible en Catálogo", default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Primero guardamos para asegurar que tenemos un ID si es nuevo (opcional, pero útil para nombres únicos)
        is_new = self._state.adding
        super().save(*args, **kwargs)

        # SOLO actuamos si hay un archivo fuente y NO hay imagen de catálogo
        if self.source_file and not self.image:
            ext = os.path.splitext(self.source_file.name)[1].lower()
            # Usar ID del producto para evitar colisiones de nombres
            file_base = f"prod_{self.id}"

            try:
                print(f"[PREVIEW] Procesando Producto #{self.id}: {self.source_file.name}")
                
                # 1. Abrir archivo fuente
                if hasattr(self.source_file, 'open'):
                    self.source_file.open('rb')
                self.source_file.seek(0)
                file_content = self.source_file.read()

                thumb_io = io.BytesIO()
                processed = False

                # 2. Convertir a WebP
                if ext == '.pdf':
                    print(f"[PREVIEW] Identificado como PDF. Intentando conversión...")
                    try:
                        try:
                            import fitz
                            print(f"[PREVIEW] fitz importado correctamente.")
                        except ImportError as ie:
                            print(f"[PREVIEW ERROR] No se pudo importar fitz: {ie}")
                            # Si fitz falla, tal vez el usuario prefiere intentar con PIL directamente si es una imagen disfrazada de PDF (raro pero posible)
                            raise ie

                        doc = fitz.open(stream=file_content, filetype="pdf")
                        print(f"[PREVIEW] PDF abierto. Páginas: {doc.page_count}")
                        
                        if doc.page_count > 0:
                            page = doc.load_page(0)
                            print(f"[PREVIEW] Primera página cargada.")
                            
                            # Matrix(2, 2) aumenta la resolución x2 para mejor calidad (approx 144 DPI)
                            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                            print(f"[PREVIEW] Pixmap generado: {pix.width}x{pix.height}")
                            
                            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                            img.save(thumb_io, format='WEBP', quality=85)
                            processed = True
                            print(f"[PREVIEW] Imagen WebP generada en memoria.")
                        else:
                            print(f"[PREVIEW ERROR] El PDF no tiene páginas.")
                        doc.close()
                    except Exception as e:
                        print(f"[PREVIEW ERROR] Falló la conversión de PDF: {str(e)}")
                        # OPCIÓN FUERA DE LA CAJA: Si el PDF falla, intentamos tratarlo como imagen 
                        # o simplemente no hacemos nada pero dejamos el log claro.
                        import traceback
                        traceback.print_exc()
                
                elif ext in ['.png', '.jpg', '.jpeg', '.webp']:
                    img = Image.open(io.BytesIO(file_content))
                    if img.mode in ('RGBA', 'LA'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[3])
                        img = background
                    else:
                        img = img.convert('RGB')
                    img.save(thumb_io, format='WEBP', quality=85)
                    processed = True

                # 3. Guardar la previsualización WebP
                if processed:
                    filename = f"{file_base}_preview.webp"
                    self.image.save(filename, ContentFile(thumb_io.getvalue()), save=False)
                    # Guardamos de nuevo SOLO el campo imagen para actualizar la DB
                    Product.objects.filter(id=self.id).update(image=self.image.name)
                    print(f"[PREVIEW] Éxito: {filename}")

            except Exception as e:
                print(f"[PREVIEW ERROR] Falló para Producto #{self.id}: {str(e)}")

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

# ... (Tus modelos anteriores Cart, etc.) ...

class ShippingAddress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    full_name = models.CharField("Nombre Completo", max_length=200)
    department = models.CharField("Departamento", max_length=100)
    city = models.CharField("Ciudad", max_length=100)
    neighborhood = models.CharField("Barrio", max_length=100)
    address_line = models.CharField("Dirección Exacta", max_length=255)
    phone = models.CharField("Teléfono", max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.city} - {self.address_line}"

# --- NUEVO MODELO DE ESTADOS ---
class OrderStatus(models.Model):
    name = models.CharField("Nombre del Estado", max_length=50) # Ej: Recibido, Descartonando
    color = models.CharField("Color (Hex)", max_length=7, default="#6B2D7B") # Para el badge
    is_default = models.BooleanField("Por defecto al crear pedido", default=False)
    
    def __str__(self): return self.name

class Order(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    address = models.ForeignKey(ShippingAddress, on_delete=models.PROTECT)
    
    # Nuevo campo de estado
    status = models.ForeignKey(OrderStatus, on_delete=models.PROTECT, null=True, blank=True)
    
    total = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    is_paid = models.BooleanField(default=False) # Mantenemos por compatibilidad

    def __str__(self):
        return f"Pedido #{self.id} - {self.status.name if self.status else 'Sin Estado'}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True) # Enlace al producto original
    product_name = models.CharField(max_length=200)
    variant_text = models.CharField(max_length=200) # Ej: "Grande - Dorado"
    quantity = models.IntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2) # Precio en el momento de compra

    def get_total(self):
        return self.price * self.quantity


# --- MODELOS PARA CARGA MASIVA ---
class BulkUploadBatch(models.Model):
    """Rastrea una sesión de carga masiva"""
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('processing', 'Procesando'),
        ('completed', 'Completado'),
        ('failed', 'Fallido'),
    ]

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    total_files = models.IntegerField(default=0)
    processed_files = models.IntegerField(default=0)
    successful_uploads = models.IntegerField(default=0)
    failed_uploads = models.IntegerField(default=0)
    error_log = models.TextField(blank=True)

    def get_progress_percentage(self):
        if self.total_files == 0:
            return 0
        return int((self.processed_files / self.total_files) * 100)

    def __str__(self):
        return f"Lote #{self.id} - {self.created_at.strftime('%Y-%m-%d %H:%M')}"

    class Meta:
        verbose_name = "Lote de Carga Masiva"
        verbose_name_plural = "Lotes de Carga Masiva"
        ordering = ['-created_at']


class BulkUploadItem(models.Model):
    """Archivo individual en un lote de carga masiva"""
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('processing', 'Procesando AI'),
        ('completed', 'Completado'),
        ('failed', 'Error'),
    ]

    batch = models.ForeignKey(BulkUploadBatch, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    original_filename = models.CharField(max_length=255)
    source_file = models.FileField(upload_to='bulk_upload_temp/')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True)
    ai_extracted_description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.original_filename} - {self.get_status_display()}"

    class Meta:
        verbose_name = "Item de Carga Masiva"
        verbose_name_plural = "Items de Carga Masiva"
        ordering = ['-created_at']


# --- MODELOS DE PEDIDOS INTERNOS ---
from products.models_internal_orders import InternalOrder, InternalOrderItem, InternalOrderGroup