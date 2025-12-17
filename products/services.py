from .models import ProductVariant, Size, Material, Color

def generar_variantes_vinilo(product):
    """
    Lee las reglas de negocio y genera automáticamente las combinaciones
    de precios para Vinilos de Corte.
    """
    # 1. Obtener los objetos de la base de datos
    sizes = Size.objects.all()
    colors = Color.objects.all()
    mat_vinilo = Material.objects.get(name="Vinilo Tradicional")
    mat_mailan = Material.objects.get(name="Mailan Metalizado")

    variants_created = 0

    # 2. Recorremos todos los tamaños y colores para crear combinaciones
    for size in sizes:
        for color in colors:
            material = mat_vinilo # Por defecto
            price = 0.00

            # --- REGLAS DE PRECIOS (Basado en tu archivo precios.txt) ---
            
            # Lógica para detectar si el color implica material Mailan
            # (En tu lista: Dorado Mailan es un material, no solo un color)
            # Aquí asumimos que si eliges un color "Especial" o el usuario lo define
            # Para simplificar, crearemos las variantes estándar y las especiales.
            
            # -- PRECIOS GRANDE (19x25cm) --
            if "Grande" in size.name:
                base_price = 1500.00
                mailan_price = 1900.00
            
            # -- PRECIOS MEDIANO (19x15cm) --
            elif "Mediano" in size.name:
                base_price = 1300.00
                mailan_price = 1600.00
                
            # -- PRECIOS PEQUEÑO (14,5x14,3cm) --
            elif "Pequeño" in size.name:
                base_price = 1150.00
                mailan_price = 1300.00
            
            else:
                continue # Si hay un tamaño raro, lo saltamos

            # CREAR VARIANTE VINILO TRADICIONAL (Para todos los colores)
            # Evitamos crear Vinilo Tradicional para colores que no existen en vinilo si fuera el caso
            # Pero según tu lista, crearemos la base.
            
            ProductVariant.objects.get_or_create(
                product=product,
                size=size,
                material=mat_vinilo,
                color=color,
                defaults={'price': base_price, 'stock': 100}
            )
            variants_created += 1

            # CREAR VARIANTE MAILAN (Solo para Dorado, o colores metalizados)
            # Según tu lista, "Dorado Mailan" es una combinación específica.
            # Vamos a crear una variante Mailan para el color Dorado.
            if color.name == "Dorado":
                ProductVariant.objects.get_or_create(
                    product=product,
                    size=size,
                    material=mat_mailan,
                    color=color,
                    defaults={'price': mailan_price, 'stock': 50}
                )
                variants_created += 1

    return variants_created

# ... (Tu función generar_variantes_vinilo sigue arriba) ...

def generar_variantes_impresos(product):
    """
    Genera precios para Stickers Impresos de Globos.
    Regla: Pequeño = 1300, Mediano = 1600.
    Material: Vinilo Impreso (Fijo). Color: Full Color (Fijo).
    """
    # 1. Asegurar que existan los atributos base para este tipo
    # Usamos get_or_create para que no falle si no existen
    mat_impreso, _ = Material.objects.get_or_create(name="Vinilo Impreso", defaults={'is_special': False})
    col_full, _ = Color.objects.get_or_create(name="Full Color", defaults={'hex_code': '#FFFFFF'}) # Blanco/Multi

    # 2. Buscar los tamaños (Asumimos que ya existen por el script anterior)
    # Buscamos por texto flexible para asegurar que los encuentre
    sizes = Size.objects.filter(name__in=["Pequeño", "Mediano"])

    created_count = 0

    for size in sizes:
        price = 0
        
        # --- REGLAS DE PRECIO ---
        if "Pequeño" in size.name:
            price = 1300.00
        elif "Mediano" in size.name:
            price = 1600.00
        
        # Si encontró precio, creamos la variante
        if price > 0:
            ProductVariant.objects.get_or_create(
                product=product,
                size=size,
                material=mat_impreso,
                color=col_full,
                defaults={'price': price, 'stock': 100}
            )
            created_count += 1
            
    return created_count