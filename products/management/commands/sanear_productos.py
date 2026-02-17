from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Max

from products.models import Color, Product, ProductVariant
from products.services import sincronizar_color_en_productos, sincronizar_variantes_producto


class Command(BaseCommand):
    help = (
        "Sanea productos y variantes: completa faltantes, sincroniza colores y "
        "desactiva duplicados antiguos."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Aplica cambios en base de datos. Sin este flag solo muestra diagnostico.",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Incluye productos inactivos en la sincronizacion de variantes/colores.",
        )
        parser.add_argument(
            "--skip-color-sync",
            action="store_true",
            help="No sincroniza colores nuevos en productos antiguos.",
        )
        parser.add_argument(
            "--skip-dedup",
            action="store_true",
            help="No desactiva productos activos duplicados por nombre + tipo.",
        )
        parser.add_argument(
            "--skip-variant-dedup",
            action="store_true",
            help="No elimina filas duplicadas exactas de variantes.",
        )

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        include_inactive = options["include_inactive"]
        skip_color_sync = options["skip_color_sync"]
        skip_dedup = options["skip_dedup"]
        skip_variant_dedup = options["skip_variant_dedup"]

        product_scope = Product.objects.all()
        if not include_inactive:
            product_scope = product_scope.filter(is_active=True)

        duplicate_product_groups = Product.objects.filter(is_active=True).values(
            "name", "product_type"
        ).annotate(total=Count("id")).filter(total__gt=1).count()

        duplicate_variant_groups = ProductVariant.objects.values(
            "product_id", "size_id", "material_id", "color_id"
        ).annotate(total=Count("id")).filter(total__gt=1).count()

        products_without_variants = product_scope.filter(variants__isnull=True).count()
        sale_colors = Color.objects.exclude(name__iexact="Full Color")

        self.stdout.write(self.style.MIGRATE_HEADING("Diagnostico de saneamiento"))
        self.stdout.write(f"- Productos objetivo: {product_scope.count()}")
        self.stdout.write(f"- Productos objetivo sin variantes: {products_without_variants}")
        self.stdout.write(f"- Grupos de productos duplicados activos: {duplicate_product_groups}")
        self.stdout.write(f"- Grupos de variantes duplicadas exactas: {duplicate_variant_groups}")
        self.stdout.write(f"- Colores de venta detectados: {sale_colors.count()}")

        if not apply_changes:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Modo solo diagnostico. Sin cambios aplicados."))
            self.stdout.write("Ejecuta con --apply para ejecutar el saneamiento.")
            return

        deactivated_products = 0
        created_variants = 0
        products_touched = 0
        created_color_variants = 0
        deleted_variant_rows = 0

        with transaction.atomic():
            if not skip_dedup:
                duplicate_groups = Product.objects.filter(is_active=True).values(
                    "name", "product_type"
                ).annotate(total=Count("id"), keep_id=Max("id")).filter(total__gt=1)

                for group in duplicate_groups.iterator():
                    updated = Product.objects.filter(
                        is_active=True,
                        name=group["name"],
                        product_type=group["product_type"],
                    ).exclude(id=group["keep_id"]).update(is_active=False, is_online=False)
                    deactivated_products += updated

            product_scope = Product.objects.all()
            if not include_inactive:
                product_scope = product_scope.filter(is_active=True)

            for product in product_scope.iterator():
                created = sincronizar_variantes_producto(product)
                if created:
                    created_variants += created
                    products_touched += 1

            if not skip_color_sync:
                for color in sale_colors.iterator():
                    created_color_variants += sincronizar_color_en_productos(
                        color,
                        only_active=not include_inactive,
                    )

            if not skip_variant_dedup:
                duplicate_variant_qs = ProductVariant.objects.values(
                    "product_id", "size_id", "material_id", "color_id"
                ).annotate(total=Count("id"), keep_id=Max("id")).filter(total__gt=1)

                for group in duplicate_variant_qs.iterator():
                    to_delete = ProductVariant.objects.filter(
                        product_id=group["product_id"],
                        size_id=group["size_id"],
                        material_id=group["material_id"],
                        color_id=group["color_id"],
                    ).exclude(id=group["keep_id"])
                    deleted_variant_rows += to_delete.count()
                    to_delete.delete()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Saneamiento completado."))
        self.stdout.write(f"- Productos desactivados por duplicado: {deactivated_products}")
        self.stdout.write(f"- Productos con variantes nuevas: {products_touched}")
        self.stdout.write(f"- Variantes nuevas por tipo de producto: {created_variants}")
        self.stdout.write(f"- Variantes nuevas por sincronizacion de colores: {created_color_variants}")
        self.stdout.write(f"- Filas de variantes duplicadas eliminadas: {deleted_variant_rows}")
