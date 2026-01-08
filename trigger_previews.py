import os
import django
import io

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from products.models import Product

def trigger_previews():
    # Buscar productos que tengan source_file pero no imagen, o forzar uno
    products = Product.objects.filter(source_file__icontains='.pdf', image='')
    if not products.exists():
        print("No se encontraron productos PDF sin imagen para procesar.")
        # Intentar con el último PDF aunque tenga imagen (forzando borrado de imagen localmente para el test)
        products = Product.objects.filter(source_file__icontains='.pdf').order_by('-id')[:1]
        if not products.exists():
            print("No hay ningún producto PDF en la base de datos.")
            return

    for p in products:
        print(f"\n--- Procesando Producto #{p.id}: {p.name} ---")
        print(f"Archivo: {p.source_file.name}")
        
        # Forzar ejecución de la lógica de previsualización
        # Borramos la imagen temporalmente en el objeto para que el save() actúe
        p.image = None
        try:
            p.save()
            print(f"Save completado para #{p.id}")
        except Exception as e:
            print(f"Error fatal en save(): {e}")

if __name__ == "__main__":
    trigger_previews()
