from decimal import Decimal

from .models import Color, Material, Product, ProductVariant, Size

DEFAULT_STOCK = 100
VINILO_BASE_PRICE_BY_SIZE = {
    "grande": Decimal("1500.00"),
    "mediano": Decimal("1300.00"),
    "peque": Decimal("1150.00"),
}
VINILO_MAILAN_PRICE_BY_SIZE = {
    "grande": Decimal("1900.00"),
    "mediano": Decimal("1600.00"),
    "peque": Decimal("1300.00"),
}
CINTA_PRICE_BY_SIZE = {
    "grande": Decimal("1500.00"),
    "mediano": Decimal("1300.00"),
    "peque": Decimal("1150.00"),
}
IMPRESO_PRICE_BY_SIZE = {
    "peque": Decimal("1300.00"),
    "mediano": Decimal("1600.00"),
}


def _price_for_size(size_name, price_map, fallback=Decimal("0")):
    normalized = (size_name or "").lower()
    for token, price in price_map.items():
        if token in normalized:
            return price
    return fallback


def _sale_colors(include_full_color=False):
    colors = Color.objects.all().order_by("name")
    if include_full_color:
        return colors
    return colors.exclude(name__iexact="Full Color")


def _resolve_price_from_existing_variant(product, size, material, fallback):
    existing = ProductVariant.objects.filter(
        product=product,
        size=size,
        material=material,
    ).exclude(price__isnull=True).order_by("-id").first()
    if existing and existing.price and existing.price > 0:
        return existing.price
    return fallback


def generar_variantes_vinilo(product):
    """
    Genera (solo las faltantes) para Vinilo de Corte:
    - Todos los colores en Vinilo Tradicional
    - Dorado en Mailan Metalizado
    """
    sizes = Size.objects.all()
    colors = _sale_colors()
    mat_vinilo, _ = Material.objects.get_or_create(name="Vinilo Tradicional", defaults={"is_special": False})
    mat_mailan, _ = Material.objects.get_or_create(name="Mailan Metalizado", defaults={"is_special": True})

    variants_created = 0
    for size in sizes:
        base_price = _price_for_size(size.name, VINILO_BASE_PRICE_BY_SIZE)
        mailan_price = _price_for_size(size.name, VINILO_MAILAN_PRICE_BY_SIZE)
        if base_price <= 0:
            continue

        for color in colors:
            _, created = ProductVariant.objects.get_or_create(
                product=product,
                size=size,
                material=mat_vinilo,
                color=color,
                defaults={"price": base_price, "stock": DEFAULT_STOCK},
            )
            if created:
                variants_created += 1

            if color.name.strip().lower() == "dorado" and mailan_price > 0:
                _, created_mailan = ProductVariant.objects.get_or_create(
                    product=product,
                    size=size,
                    material=mat_mailan,
                    color=color,
                    defaults={"price": mailan_price, "stock": 50},
                )
                if created_mailan:
                    variants_created += 1

    return variants_created


def generar_variantes_cinta(product):
    """
    Genera (solo las faltantes) para Cintas:
    - Todos los tamanos
    - Todos los colores de venta (excepto Full Color)
    - Material base Vinilo Tradicional
    """
    sizes = Size.objects.all()
    colors = _sale_colors()
    mat_vinilo, _ = Material.objects.get_or_create(name="Vinilo Tradicional", defaults={"is_special": False})

    created_count = 0
    for size in sizes:
        base_price = _price_for_size(size.name, CINTA_PRICE_BY_SIZE)
        if base_price <= 0:
            continue
        for color in colors:
            _, created = ProductVariant.objects.get_or_create(
                product=product,
                size=size,
                material=mat_vinilo,
                color=color,
                defaults={"price": base_price, "stock": DEFAULT_STOCK},
            )
            if created:
                created_count += 1
    return created_count


def generar_variantes_impresos(product):
    """
    Genera (solo las faltantes) para Impresos:
    - Material fijo: Vinilo Impreso
    - Color fijo: Full Color
    - Tamanos con precio definido
    """
    mat_impreso, _ = Material.objects.get_or_create(name="Vinilo Impreso", defaults={"is_special": False})
    col_full, _ = Color.objects.get_or_create(name="Full Color", defaults={"hex_code": "#FFFFFF"})
    sizes = Size.objects.all()

    created_count = 0
    for size in sizes:
        price = _price_for_size(size.name, IMPRESO_PRICE_BY_SIZE)
        if price <= 0:
            continue

        _, created = ProductVariant.objects.get_or_create(
            product=product,
            size=size,
            material=mat_impreso,
            color=col_full,
            defaults={"price": price, "stock": DEFAULT_STOCK},
        )
        if created:
            created_count += 1

    return created_count


def sincronizar_variantes_producto(product):
    """
    Garantiza que un producto tenga sus variantes minimas segun tipo.
    Retorna cuantas variantes nuevas se crearon.
    """
    if product.product_type == "vinilo_corte":
        return generar_variantes_vinilo(product)
    if product.product_type == "impreso_globo":
        return generar_variantes_impresos(product)
    if product.product_type == "cinta":
        return generar_variantes_cinta(product)
    return 0


def sincronizar_color_en_productos(color, only_active=True):
    """
    Agrega un color nuevo a productos antiguos de tipos que trabajan por color.
    Regla:
    - vinilo_corte: agrega color sobre Vinilo Tradicional
    - cinta: agrega color sobre Vinilo Tradicional
    """
    if not color:
        return 0

    products = Product.objects.filter(product_type__in=["vinilo_corte", "cinta"])
    if only_active:
        products = products.filter(is_active=True)

    mat_vinilo, _ = Material.objects.get_or_create(name="Vinilo Tradicional", defaults={"is_special": False})
    sizes = Size.objects.all()
    created_count = 0

    for product in products:
        price_map = VINILO_BASE_PRICE_BY_SIZE if product.product_type == "vinilo_corte" else CINTA_PRICE_BY_SIZE
        for size in sizes:
            fallback = _price_for_size(size.name, price_map, Decimal("0"))
            if fallback <= 0:
                continue
            resolved_price = _resolve_price_from_existing_variant(
                product=product,
                size=size,
                material=mat_vinilo,
                fallback=fallback,
            )
            _, created = ProductVariant.objects.get_or_create(
                product=product,
                size=size,
                material=mat_vinilo,
                color=color,
                defaults={"price": resolved_price, "stock": DEFAULT_STOCK},
            )
            if created:
                created_count += 1

    return created_count
