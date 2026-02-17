from django.core.management.base import BaseCommand

from products.models import Color, Product
from products.services import sincronizar_color_en_productos, sincronizar_variantes_producto


class Command(BaseCommand):
    help = (
        "Sincroniza variantes de catalogo para produccion: "
        "repara variantes faltantes (incluye cintas) y propaga colores."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--product-type",
            action="append",
            choices=["cinta", "vinilo_corte", "impreso_globo"],
            default=["cinta"],
            help=(
                "Tipo de producto a sincronizar. Puede repetirse. "
                "Por defecto: cinta"
            ),
        )
        parser.add_argument(
            "--all-product-types",
            action="store_true",
            help="Sincroniza todos los tipos soportados (vinilo_corte, cinta, impreso_globo).",
        )
        parser.add_argument(
            "--color",
            action="append",
            default=["Fucsia"],
            help="Color a sincronizar (puede repetirse). Ej: --color Fucsia --color Rojo",
        )
        parser.add_argument(
            "--all-sale-colors",
            action="store_true",
            help="Sincroniza todos los colores de venta (excepto Full Color).",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Incluye productos inactivos en la sincronizacion.",
        )

    def handle(self, *args, **options):
        only_active = not options["include_inactive"]
        selected_types = list(dict.fromkeys(options["product_type"]))
        if options["all_product_types"]:
            selected_types = ["vinilo_corte", "cinta", "impreso_globo"]

        products = Product.objects.filter(product_type__in=selected_types)
        if only_active:
            products = products.filter(is_active=True)

        self.stdout.write(self.style.MIGRATE_HEADING("Sincronizando variantes por producto"))
        products_touched = 0
        variants_created = 0
        for product in products.iterator():
            created = sincronizar_variantes_producto(product) or 0
            if created:
                products_touched += 1
                variants_created += created

        colors = []
        if options["all_sale_colors"]:
            colors = list(Color.objects.exclude(name__iexact="Full Color").order_by("name"))
        else:
            seen = set()
            for raw_name in options["color"]:
                name = (raw_name or "").strip()
                if not name:
                    continue
                key = name.lower()
                if key in seen:
                    continue
                seen.add(key)
                color = Color.objects.filter(name__iexact=name).first()
                if not color:
                    self.stdout.write(self.style.WARNING(f"Color no encontrado: {name}"))
                    continue
                colors.append(color)

        self.stdout.write(self.style.MIGRATE_HEADING("Sincronizando colores en productos"))
        color_variants_created = 0
        for color in colors:
            created = sincronizar_color_en_productos(color, only_active=only_active) or 0
            color_variants_created += created
            self.stdout.write(f"- {color.name}: {created} variantes nuevas")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Sincronizacion completada"))
        self.stdout.write(f"- Tipos sincronizados: {', '.join(selected_types)}")
        self.stdout.write(f"- Productos evaluados: {products.count()}")
        self.stdout.write(f"- Productos con variantes nuevas: {products_touched}")
        self.stdout.write(f"- Variantes nuevas por tipo de producto: {variants_created}")
        self.stdout.write(f"- Variantes nuevas por sincronizacion de color: {color_variants_created}")
