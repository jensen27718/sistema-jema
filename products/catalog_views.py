import os
import io
import json
import math
import requests as http_requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST
from .models import Product, Category

# ── Constantes de diseño ──────────────────────────────────────────────
W, H = 1080, 1920  # Instagram Story 9:16

# Paleta minimalista lavanda
LAVENDER_LIGHT = (230, 220, 245)
LAVENDER       = (200, 180, 220)
LAVENDER_DARK  = (150, 130, 180)
PURPLE_SOFT    = (120, 90, 160)
PURPLE_DEEP    = (80, 50, 120)
TEAL           = (64, 180, 180)
TEAL_SOFT      = (100, 200, 200)
WHITE          = (255, 255, 255)
WHITE_90       = (255, 255, 255, 230)
WHITE_70       = (255, 255, 255, 180)
WHITE_50       = (255, 255, 255, 128)
DARK_TEXT      = (60, 40, 80)

# ── Helpers ───────────────────────────────────────────────────────────
FONT_DIR = os.path.join(settings.BASE_DIR, 'static', 'fonts')


def _font(weight='Regular', size=40):
    path = os.path.join(FONT_DIR, f'Poppins-{weight}.ttf')
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def _gradient_smooth(size, color_top, color_bottom):
    """Genera un gradiente vertical suave con mejor difuminado."""
    img = Image.new('RGB', size)
    draw = ImageDraw.Draw(img)
    h = size[1]
    for y in range(h):
        ratio = y / h
        ratio = ratio * ratio * (3 - 2 * ratio)
        r = int(color_top[0] + (color_bottom[0] - color_top[0]) * ratio)
        g = int(color_top[1] + (color_bottom[1] - color_top[1]) * ratio)
        b = int(color_top[2] + (color_bottom[2] - color_top[2]) * ratio)
        draw.line([(0, y), (size[0], y)], fill=(r, g, b))
    img = img.filter(ImageFilter.GaussianBlur(radius=3))
    return img


def _rounded_rect(draw, xy, radius, fill):
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def _center_text(draw, text, y, font, fill, width=W):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (width - tw) // 2
    draw.text((x, y), text, font=font, fill=fill)


def _wrap_text(text, font, max_width):
    words = text.split()
    lines = []
    current = ""
    tmp = Image.new('RGB', (1, 1))
    draw = ImageDraw.Draw(tmp)
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _load_product_image(product):
    if not product.image:
        return None
    try:
        url = product.image.url
        if url.startswith('http'):
            resp = http_requests.get(url, timeout=10)
            if resp.status_code == 200:
                return Image.open(io.BytesIO(resp.content)).convert('RGBA')
        else:
            path = product.image.path
            if os.path.exists(path):
                return Image.open(path).convert('RGBA')
    except Exception:
        pass
    return None


def _draw_soft_glow(img, cx, cy, radius, color, alpha=30):
    glow = Image.new('RGBA', (radius * 2, radius * 2), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    for i in range(radius, 0, -3):
        a = int(alpha * (i / radius) ** 2)
        glow_draw.ellipse([radius - i, radius - i, radius + i, radius + i],
                          fill=(*color[:3], a))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=radius // 3))
    img.paste(glow, (cx - radius, cy - radius), glow)


def _draw_arrow_down(draw, cx, cy, size, color):
    half = size // 2
    draw.polygon([
        (cx, cy + half),
        (cx - half, cy - half),
        (cx + half, cy - half)
    ], fill=color)


def _draw_whatsapp_icon(draw, cx, cy, size, color):
    outer_r = size // 2
    inner_r = size // 2 - 4
    draw.ellipse([cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r], fill=color)
    draw.ellipse([cx - inner_r + 3, cy - inner_r + 3, cx + inner_r - 3, cy + inner_r - 3], fill=color)
    phone_size = size // 3
    draw.arc([cx - phone_size, cy - phone_size, cx + phone_size, cy + phone_size],
             start=200, end=340, fill=WHITE, width=4)
    bubble_x = cx + size // 4
    bubble_y = cy + size // 3
    draw.polygon([
        (bubble_x, bubble_y),
        (bubble_x - 8, bubble_y + 12),
        (bubble_x + 4, bubble_y + 8)
    ], fill=color)


def _create_cover(catalog_name, catalog_type, phone, product_count):
    page = _gradient_smooth((W, H), LAVENDER_LIGHT, LAVENDER_DARK)
    page = page.convert('RGBA')
    page = page.filter(ImageFilter.GaussianBlur(radius=5))
    draw = ImageDraw.Draw(page, 'RGBA')

    _draw_soft_glow(page, W - 150, 200, 250, LAVENDER, 15)
    _draw_soft_glow(page, 150, H - 400, 200, PURPLE_SOFT, 12)
    draw = ImageDraw.Draw(page, 'RGBA')

    y = 200
    _center_text(draw, "JEMA", y, _font('Bold', 48), PURPLE_DEEP)
    _center_text(draw, "Stickers", y + 55, _font('Light', 28), PURPLE_SOFT)

    y = 480
    name_font = _font('ExtraBold', 72)
    lines = _wrap_text(catalog_name.upper(), name_font, W - 120)
    for line in lines[:3]:
        _center_text(draw, line, y, name_font, PURPLE_DEEP)
        y += 90

    y += 30
    _center_text(draw, catalog_type, y, _font('Medium', 36), TEAL)

    y += 100
    _center_text(draw, f"{product_count} productos", y, _font('SemiBold', 32), WHITE)

    arrow_y = y + 100
    _draw_arrow_down(draw, W // 2, arrow_y, 30, TEAL)

    footer_y = H - 280
    line_w = 200
    draw.rectangle([(W - line_w) // 2, footer_y, (W + line_w) // 2, footer_y + 3], fill=TEAL)

    footer_y += 40
    _center_text(draw, "VENTA EXCLUSIVA MAYORISTAS", footer_y, _font('Medium', 26), PURPLE_DEEP)

    footer_y += 60
    icon_size = 36
    icon_cx = W // 2 - 130
    _draw_whatsapp_icon(draw, icon_cx, footer_y + 20, icon_size, TEAL)
    draw.text((icon_cx + 40, footer_y), phone, font=_font('Bold', 42), fill=PURPLE_DEEP)

    _center_text(draw, "2025", H - 80, _font('Light', 24), PURPLE_SOFT)

    return page.convert('RGB')


def _create_product_page(product1, product2, page_num, total_pages):
    page = _gradient_smooth((W, H), LAVENDER_LIGHT, LAVENDER)
    page = page.convert('RGBA')
    page = page.filter(ImageFilter.GaussianBlur(radius=4))
    draw = ImageDraw.Draw(page, 'RGBA')

    draw.rectangle([0, 0, W, 100], fill=(*PURPLE_DEEP, 240))
    draw.text((40, 28), "JEMA", font=_font('Bold', 38), fill=WHITE)
    
    page_text = f"{page_num}/{total_pages}"
    bbox = draw.textbbox((0, 0), page_text, font=_font('Medium', 26))
    draw.text((W - (bbox[2] - bbox[0]) - 40, 34), page_text, font=_font('Medium', 26), fill=WHITE_70)

    card_margin = 35
    card_w = W - card_margin * 2
    card_radius = 25

    products = [p for p in [product1, product2] if p is not None]
    
    if len(products) == 1:
        card_h = 1680
    else:
        card_h = 820

    for idx, product in enumerate(products):
        card_y = 130 + idx * (card_h + 25)

        _rounded_rect(draw, [card_margin, card_y, card_margin + card_w, card_y + card_h], card_radius, WHITE)
        draw.rounded_rectangle([card_margin, card_y, card_margin + card_w, card_y + card_h],
                               radius=card_radius, outline=(*LAVENDER_DARK, 80), width=1)

        info_h = 200
        img_area_h = card_h - info_h - 30
        img_area_y = card_y + 20
        product_img = _load_product_image(product)

        if product_img:
            max_w = card_w - 50
            max_h = img_area_h - 20
            img_w, img_h = product_img.size
            ratio = min(max_w / img_w, max_h / img_h)
            new_w = int(img_w * ratio)
            new_h = int(img_h * ratio)
            product_img = product_img.resize((new_w, new_h), Image.LANCZOS)

            img_x = card_margin + (card_w - new_w) // 2
            img_y = img_area_y + (img_area_h - new_h) // 2

            page.paste(product_img, (img_x, img_y), product_img)
            draw = ImageDraw.Draw(page, 'RGBA')
        else:
            _center_text(draw, "Sin imagen", img_area_y + img_area_h // 2 - 15, _font('Regular', 32), LAVENDER_DARK)

        info_y = card_y + card_h - info_h
        draw.rectangle([card_margin + 30, info_y, card_margin + card_w - 30, info_y + 3], fill=TEAL)

        cats = product.categories.all()
        cat_text = " · ".join([c.name.upper() for c in cats]) if cats else "GENERAL"
        _center_text(draw, cat_text, info_y + 25, _font('SemiBold', 26), TEAL, W)

        name_font = _font('Bold', 40)
        ref_text = product.name.upper()
        ref_lines = _wrap_text(ref_text, name_font, card_w - 60)
        ref_y = info_y + 70
        
        for line in ref_lines[:2]:
            _center_text(draw, line, ref_y, name_font, PURPLE_DEEP, W)
            ref_y += 50

        _center_text(draw, "REFERENCIA", ref_y + 15, _font('Regular', 20), PURPLE_SOFT, W)

    footer_y = H - 55
    draw.rectangle([0, footer_y, W, H], fill=(*PURPLE_DEEP, 200))
    _center_text(draw, "JEMA · Stickers que destacan tu negocio", footer_y + 14, _font('Medium', 20), WHITE_90)

    return page.convert('RGB')


def _create_back_cover(phone):
    page = _gradient_smooth((W, H), LAVENDER, PURPLE_SOFT)
    page = page.convert('RGBA')
    page = page.filter(ImageFilter.GaussianBlur(radius=5))
    draw = ImageDraw.Draw(page, 'RGBA')

    _draw_soft_glow(page, W // 2, H // 2 - 100, 350, LAVENDER_LIGHT, 20)
    draw = ImageDraw.Draw(page, 'RGBA')

    y = 550
    _center_text(draw, "¡Gracias!", y, _font('ExtraBold', 90), WHITE)
    
    y += 130
    line_w = 150
    draw.rectangle([(W - line_w) // 2, y, (W + line_w) // 2, y + 4], fill=TEAL)
    
    y += 50
    _center_text(draw, "¿Te interesa algún diseño?", y, _font('Regular', 36), WHITE_90)
    y += 55
    _center_text(draw, "Contáctanos, con gusto te asesoramos", y, _font('Light', 28), WHITE_70)

    y += 120
    _center_text(draw, "WHATSAPP", y, _font('SemiBold', 28), TEAL_SOFT)
    y += 55
    _center_text(draw, phone, y, _font('Bold', 60), WHITE)

    _center_text(draw, "JEMA", H - 200, _font('Bold', 50), WHITE_50)
    _center_text(draw, "Stickers que destacan tu negocio", H - 140, _font('Light', 24), WHITE_50)
    _center_text(draw, "2025", H - 80, _font('Light', 22), WHITE_50)

    return page.convert('RGB')


def is_staff(user):
    return user.is_staff or user.is_superuser


@login_required
@user_passes_test(is_staff)
def catalog_selection_view(request):
    categories = Category.objects.all()
    product_types = Product.TYPE_CHOICES
    return render(request, 'dashboard/catalogs/selection.html', {
        'categories': categories,
        'product_types': product_types
    })


@login_required
@user_passes_test(is_staff)
def generate_catalog_pdf_view(request):
    catalog_name = request.POST.get('catalog_name', 'Catálogo de Productos')
    product_type = request.POST.get('product_type')
    category_ids = request.POST.getlist('categories')
    phone = request.POST.get('phone', '321 216 5252')

    # Si vienen product_ids (del editor D&D), usar esos en ese orden
    product_ids = request.POST.getlist('product_ids')
    if product_ids:
        products_qs = Product.objects.filter(id__in=product_ids, is_active=True)
        # Preservar el orden del editor
        id_order = {int(pid): idx for idx, pid in enumerate(product_ids)}
        products = sorted(list(products_qs), key=lambda p: id_order.get(p.id, 999))
    else:
        products_qs = Product.objects.filter(is_active=True)
        if product_type:
            products_qs = products_qs.filter(product_type=product_type)
        if category_ids:
            products_qs = products_qs.filter(categories__id__in=category_ids).distinct()
        products = list(products_qs.order_by('name'))

    type_label = "General"
    if product_type:
        type_label = dict(Product.TYPE_CHOICES).get(product_type, "General")

    pages = []
    pages.append(_create_cover(catalog_name, type_label, phone, len(products)))

    total_product_pages = math.ceil(len(products) / 2) if products else 0
    for i in range(0, len(products), 2):
        p1 = products[i]
        p2 = products[i + 1] if i + 1 < len(products) else None
        page_num = (i // 2) + 1
        pages.append(_create_product_page(p1, p2, page_num, total_product_pages))

    pages.append(_create_back_cover(phone))

    pdf_buffer = io.BytesIO()
    if pages:
        pages[0].save(
            pdf_buffer,
            format='PDF',
            save_all=True,
            append_images=pages[1:],
            resolution=150.0
        )

    pdf_buffer.seek(0)
    filename = f"Catalogo_{catalog_name.replace(' ', '_')}.pdf"
    response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@user_passes_test(is_staff)
def catalog_editor_view(request):
    """Editor drag & drop para catálogos personalizados"""
    categories = Category.objects.all()
    product_types = Product.TYPE_CHOICES
    return render(request, 'dashboard/catalogs/editor.html', {
        'categories': categories,
        'product_types': product_types,
    })


@login_required
@user_passes_test(is_staff)
@require_POST
def api_catalog_filter_products(request):
    """API para filtrar productos activos y retornar JSON"""
    data = json.loads(request.body)
    search = data.get('search', '').strip()
    product_type = data.get('product_type', '')
    category_id = data.get('category_id', '')

    products = Product.objects.filter(is_active=True)
    if search:
        products = products.filter(name__icontains=search)
    if product_type:
        products = products.filter(product_type=product_type)
    if category_id:
        products = products.filter(categories__id=category_id)

    products = products.distinct().order_by('name')[:100]

    results = []
    for p in products:
        cats = [c.name for c in p.categories.all()]
        results.append({
            'id': p.id,
            'name': p.name,
            'image_url': p.image.url if p.image else None,
            'categories': cats,
            'product_type': p.get_product_type_display(),
        })

    return JsonResponse({'ok': True, 'products': results})
