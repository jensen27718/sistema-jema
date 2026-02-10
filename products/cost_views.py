"""Views and APIs for manual order costs."""
import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction as db_transaction
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from contabilidad.models import Account, Transaction, TransactionCategory
from products.models import Order, ProductVariant
from products.models_costs import CostType, OrderCostBreakdown
from products.models_internal_orders import InternalOrder

logger = logging.getLogger(__name__)


def is_staff(user):
    return user.is_staff


def _parse_decimal(raw_value, default=Decimal("0")):
    if raw_value in (None, "", "null"):
        return default
    value = str(raw_value).replace(",", ".")
    return Decimal(value)


def _parse_date(raw_value):
    if not raw_value:
        return timezone.localdate()
    return date.fromisoformat(raw_value)


def _resolve_order(order_type, order_id):
    if order_type == "internal":
        return get_object_or_404(InternalOrder, id=order_id)
    if order_type == "catalog":
        return get_object_or_404(Order, id=order_id)
    raise ValueError("order_type invalido")


def _resolve_order_context_from_breakdown(breakdown):
    if breakdown.internal_order_id:
        return "internal", breakdown.internal_order
    return "catalog", breakdown.order


def _get_order_breakdowns(order, order_type):
    if order_type == "internal":
        return (
            OrderCostBreakdown.objects.filter(internal_order=order)
            .select_related("cost_type", "accounting_category", "accounting_transaction")
            .order_by("-created_at")
        )
    return (
        OrderCostBreakdown.objects.filter(order=order)
        .select_related("cost_type", "accounting_category", "accounting_transaction")
        .order_by("-created_at")
    )


def _get_sale_total(order, order_type):
    if order_type == "internal":
        return order.total_estimated or Decimal("0")
    return order.total or Decimal("0")


def _build_totals(order, order_type):
    breakdowns = _get_order_breakdowns(order, order_type)
    total_costs = breakdowns.aggregate(total=Sum("total"))["total"] or Decimal("0")
    shipping = order.shipping_cost or Decimal("0")
    sale_total = _get_sale_total(order, order_type)
    grand_total = total_costs + shipping
    margin = sale_total - grand_total
    return {
        "total_costs": total_costs,
        "shipping": shipping,
        "sale_total": sale_total,
        "grand_total": grand_total,
        "margin": margin,
        "total_items_income": getattr(order, 'total_items_price', Decimal("0")) if order_type == 'internal' else sale_total,
        "discount_amount": getattr(order, 'discount_amount', Decimal("0")),
    }


def _serialize_breakdown(breakdown):
    return {
        "id": breakdown.id,
        "cost_type_id": breakdown.cost_type_id,
        "cost_type_name": breakdown.cost_type.name if breakdown.cost_type_id else "",
        "description": breakdown.description,
        "quantity": str(breakdown.calculated_quantity),
        "unit_price": str(breakdown.unit_price),
        "total": str(breakdown.total),
        "notes": breakdown.notes or "",
        "accounting_category_id": breakdown.accounting_category_id,
        "accounting_category_name": breakdown.accounting_category.name if breakdown.accounting_category_id else "",
        "accounting_status": breakdown.accounting_status,
        "accounting_status_display": breakdown.get_accounting_status_display(),
        "accounting_transaction_id": breakdown.accounting_transaction_id,
        "accounting_posted_at": breakdown.accounting_posted_at.isoformat() if breakdown.accounting_posted_at else None,
        "can_edit": breakdown.accounting_status == OrderCostBreakdown.ACCOUNTING_STATUS_PENDING,
        "can_delete": breakdown.accounting_status == OrderCostBreakdown.ACCOUNTING_STATUS_PENDING,
        "can_post": breakdown.accounting_status == OrderCostBreakdown.ACCOUNTING_STATUS_PENDING and breakdown.total > 0,
    }


def _totals_payload(order, order_type):
    totals = _build_totals(order, order_type)
    return {
        "total_costs": str(totals["total_costs"]),
        "shipping": str(totals["shipping"]),
        "sale_total": str(totals["sale_total"]),
        "grand_total": str(totals["grand_total"]),
        "margin": str(totals["margin"]),
        "total_items_income": str(totals["total_items_income"]),
        "discount_amount": str(totals["discount_amount"]),
    }


def _default_transaction_description(breakdown):
    if breakdown.order_id:
        return f"Gasto pedido #{breakdown.order_id} - {breakdown.description}"
    return f"Gasto pedido interno #{breakdown.internal_order_id} - {breakdown.description}"


@login_required
@user_passes_test(is_staff)
def cost_config_view(request):
    """Cost type configuration page for manual order expenses."""
    cost_types = CostType.objects.select_related("accounting_category").all()
    categories_expense = TransactionCategory.objects.filter(transaction_type="egreso").order_by("name")
    return render(
        request,
        "dashboard/costs/config.html",
        {
            "cost_types": cost_types,
            "categories_expense": categories_expense,
        },
    )


@login_required
@user_passes_test(is_staff)
@require_POST
def api_create_cost_type(request):
    try:
        data = json.loads(request.body)
        val = data.get("default_unit_price")
        if val in (None, ""):
            val = 0

        accounting_category = None
        accounting_category_id = data.get("accounting_category_id")
        if accounting_category_id not in (None, "", "null"):
            accounting_category = get_object_or_404(
                TransactionCategory, id=accounting_category_id, transaction_type="egreso"
            )

        ct = CostType.objects.create(
            name=data.get("name", "").strip(),
            unit=data.get("unit", "unidad"),
            default_unit_price=Decimal(str(val).replace(",", ".")),
            description=data.get("description", ""),
            is_active=data.get("is_active", True),
            accounting_category=accounting_category,
        )
        return JsonResponse(
            {
                "ok": True,
                "id": ct.id,
                "name": ct.name,
                "unit": ct.unit,
                "unit_display": ct.get_unit_display(),
                "default_unit_price": str(ct.default_unit_price),
                "is_active": ct.is_active,
                "accounting_category_id": ct.accounting_category_id,
                "accounting_category_name": ct.accounting_category.name if ct.accounting_category_id else "",
            }
        )
    except Exception as exc:  # pragma: no cover - guarded API error
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


@login_required
@user_passes_test(is_staff)
@require_POST
def api_update_cost_type(request):
    try:
        data = json.loads(request.body)
        ct = get_object_or_404(CostType, id=data.get("id"))
        if "name" in data:
            ct.name = data["name"]
        if "unit" in data:
            ct.unit = data["unit"]
        if "default_unit_price" in data:
            val = data["default_unit_price"]
            ct.default_unit_price = Decimal(str(val).replace(",", ".")) if val not in (None, "") else 0
        if "description" in data:
            ct.description = data["description"]
        if "is_active" in data:
            ct.is_active = data["is_active"]
        if "special_material_price" in data:
            val = data["special_material_price"]
            ct.special_material_price = Decimal(str(val).replace(",", ".")) if val not in (None, "") else 0
        if "accounting_category_id" in data:
            category_id = data["accounting_category_id"]
            if category_id in (None, "", "null"):
                ct.accounting_category = None
            else:
                ct.accounting_category = get_object_or_404(
                    TransactionCategory, id=category_id, transaction_type="egreso"
                )
        ct.save()
        return JsonResponse(
            {
                "ok": True,
                "id": ct.id,
                "name": ct.name,
                "unit": ct.unit,
                "unit_display": ct.get_unit_display(),
                "default_unit_price": str(ct.default_unit_price),
                "is_active": ct.is_active,
                "accounting_category_id": ct.accounting_category_id,
                "accounting_category_name": ct.accounting_category.name if ct.accounting_category_id else "",
            }
        )
    except Exception as exc:  # pragma: no cover - guarded API error
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


@login_required
@user_passes_test(is_staff)
@require_POST
def api_delete_cost_type(request):
    try:
        data = json.loads(request.body)
        ct = get_object_or_404(CostType, id=data.get("id"))
        ct.delete()
        return JsonResponse({"ok": True})
    except Exception as exc:  # pragma: no cover - guarded API error
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


@login_required
@user_passes_test(is_staff)
@require_POST
def api_get_order_costs(request):
    try:
        data = json.loads(request.body)
        order_type = data.get("order_type", "internal")
        order_id = data.get("order_id")
        order = _resolve_order(order_type, order_id)
        breakdowns = _get_order_breakdowns(order, order_type)
        return JsonResponse(
            {
                "ok": True,
                "breakdowns": [_serialize_breakdown(item) for item in breakdowns],
                **_totals_payload(order, order_type),
            }
        )
    except Exception as exc:
        logger.exception("Error listing manual order costs")
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


@login_required
@user_passes_test(is_staff)
@require_POST
def api_create_order_cost(request):
    try:
        data = json.loads(request.body)
        order_type = data.get("order_type", "internal")
        order_id = data.get("order_id")
        order = _resolve_order(order_type, order_id)

        cost_type = get_object_or_404(CostType, id=data.get("cost_type_id"), is_active=True)

        quantity = _parse_decimal(data.get("calculated_quantity"), default=Decimal("1"))
        unit_price = _parse_decimal(data.get("unit_price"), default=cost_type.default_unit_price or Decimal("0"))
        if data.get("total") not in (None, "", "null"):
            total = _parse_decimal(data.get("total"))
        else:
            total = quantity * unit_price

        if quantity < 0 or unit_price < 0 or total < 0:
            return JsonResponse({"ok": False, "error": "No se permiten valores negativos"}, status=400)

        accounting_category_id = data.get("accounting_category_id")
        if accounting_category_id in (None, "", "null"):
            accounting_category = cost_type.accounting_category
        else:
            accounting_category = get_object_or_404(
                TransactionCategory, id=accounting_category_id, transaction_type="egreso"
            )

        payload = {
            "cost_type": cost_type,
            "description": (data.get("description") or cost_type.name).strip(),
            "calculated_quantity": quantity or Decimal("1"),
            "unit_price": unit_price,
            "total": total,
            "is_manual": True,
            "notes": (data.get("notes") or "").strip(),
            "accounting_category": accounting_category,
            "accounting_status": OrderCostBreakdown.ACCOUNTING_STATUS_PENDING,
        }
        if order_type == "internal":
            payload["internal_order"] = order
            breakdown = OrderCostBreakdown.objects.create(**payload)
            order.recalculate_totals()
        else:
            payload["order"] = order
            breakdown = OrderCostBreakdown.objects.create(**payload)

        return JsonResponse(
            {
                "ok": True,
                "breakdown": _serialize_breakdown(breakdown),
                **_totals_payload(order, order_type),
            }
        )
    except (InvalidOperation, ValueError) as exc:
        return JsonResponse({"ok": False, "error": f"Valor invalido: {exc}"}, status=400)
    except Exception as exc:  # pragma: no cover - guarded API error
        logger.exception("Error creating manual order cost")
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


@login_required
@user_passes_test(is_staff)
@require_POST
def api_update_order_cost(request):
    try:
        data = json.loads(request.body)
        breakdown = get_object_or_404(
            OrderCostBreakdown.objects.select_related("cost_type", "order", "internal_order"),
            id=data.get("breakdown_id"),
        )

        locked_fields = {"cost_type_id", "description", "calculated_quantity", "unit_price", "total", "accounting_category_id"}
        if breakdown.accounting_status == OrderCostBreakdown.ACCOUNTING_STATUS_POSTED:
            touched_locked_fields = [field for field in locked_fields if field in data]
            if touched_locked_fields:
                return JsonResponse(
                    {
                        "ok": False,
                        "error": "No puedes editar un gasto ya registrado en contabilidad.",
                    },
                    status=400,
                )

        update_fields = []

        if "cost_type_id" in data:
            breakdown.cost_type = get_object_or_404(CostType, id=data["cost_type_id"], is_active=True)
            update_fields.append("cost_type")
            if "accounting_category_id" not in data and breakdown.cost_type.accounting_category_id:
                breakdown.accounting_category = breakdown.cost_type.accounting_category
                update_fields.append("accounting_category")

        if "description" in data:
            breakdown.description = (data.get("description") or "").strip()
            update_fields.append("description")

        if "calculated_quantity" in data:
            breakdown.calculated_quantity = _parse_decimal(data.get("calculated_quantity"), default=Decimal("1"))
            if breakdown.calculated_quantity < 0:
                return JsonResponse({"ok": False, "error": "Cantidad invalida"}, status=400)
            update_fields.append("calculated_quantity")

        if "unit_price" in data:
            breakdown.unit_price = _parse_decimal(data.get("unit_price"), default=Decimal("0"))
            if breakdown.unit_price < 0:
                return JsonResponse({"ok": False, "error": "Precio invalido"}, status=400)
            update_fields.append("unit_price")

        if "total" in data:
            breakdown.total = _parse_decimal(data.get("total"), default=Decimal("0"))
            if breakdown.total < 0:
                return JsonResponse({"ok": False, "error": "Total invalido"}, status=400)
            update_fields.append("total")
        elif "unit_price" in data or "calculated_quantity" in data:
            breakdown.total = breakdown.calculated_quantity * breakdown.unit_price
            update_fields.append("total")

        if "notes" in data:
            breakdown.notes = data.get("notes") or ""
            update_fields.append("notes")

        if "accounting_category_id" in data:
            category_id = data.get("accounting_category_id")
            if category_id in (None, "", "null"):
                breakdown.accounting_category = None
            else:
                breakdown.accounting_category = get_object_or_404(
                    TransactionCategory, id=category_id, transaction_type="egreso"
                )
            update_fields.append("accounting_category")

        if update_fields:
            breakdown.save(update_fields=list(set(update_fields)))
            order_type, order = _resolve_order_context_from_breakdown(breakdown)
            if order_type == "internal":
                order.recalculate_totals()

        order_type, order = _resolve_order_context_from_breakdown(breakdown)
        return JsonResponse(
            {
                "ok": True,
                "breakdown": _serialize_breakdown(breakdown),
                **_totals_payload(order, order_type),
            }
        )
    except (InvalidOperation, ValueError) as exc:
        return JsonResponse({"ok": False, "error": f"Valor invalido: {exc}"}, status=400)
    except Exception as exc:  # pragma: no cover - guarded API error
        logger.exception("Error updating manual order cost")
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


@login_required
@user_passes_test(is_staff)
@require_POST
def api_delete_order_cost(request):
    try:
        data = json.loads(request.body)
        breakdown = get_object_or_404(OrderCostBreakdown, id=data.get("breakdown_id"))

        if breakdown.accounting_status == OrderCostBreakdown.ACCOUNTING_STATUS_POSTED:
            return JsonResponse(
                {"ok": False, "error": "No puedes eliminar un gasto ya registrado en contabilidad."},
                status=400,
            )

        order_type, order = _resolve_order_context_from_breakdown(breakdown)
        breakdown.delete()
        if order_type == "internal":
            order.recalculate_totals()
        return JsonResponse({"ok": True, **_totals_payload(order, order_type)})
    except Exception as exc:  # pragma: no cover - guarded API error
        logger.exception("Error deleting manual order cost")
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


@login_required
@user_passes_test(is_staff)
@require_POST
def api_post_order_cost_to_accounting(request):
    try:
        data = json.loads(request.body)
        with db_transaction.atomic():
            breakdown = get_object_or_404(
                OrderCostBreakdown.objects.select_for_update().select_related("cost_type", "order", "internal_order"),
                id=data.get("breakdown_id"),
            )

            if breakdown.accounting_status == OrderCostBreakdown.ACCOUNTING_STATUS_POSTED:
                return JsonResponse({"ok": False, "error": "Este gasto ya esta registrado en contabilidad."}, status=400)

            if breakdown.total <= 0:
                return JsonResponse({"ok": False, "error": "El gasto debe tener total mayor a cero."}, status=400)

            account = get_object_or_404(Account.objects.select_for_update(), id=data.get("account_id"))

            category_id = data.get("category_id")
            if category_id in (None, "", "null"):
                category_id = breakdown.accounting_category_id or breakdown.cost_type.accounting_category_id

            if not category_id:
                return JsonResponse(
                    {"ok": False, "error": "Selecciona una categoria contable para registrar este gasto."},
                    status=400,
                )

            category = get_object_or_404(TransactionCategory, id=category_id, transaction_type="egreso")

            movement_date = _parse_date(data.get("date"))
            txn_description = (data.get("description") or "").strip() or _default_transaction_description(breakdown)

            transaction_payload = {
                "account": account,
                "category": category,
                "amount": breakdown.total,
                "description": txn_description,
                "date": movement_date,
            }
            if breakdown.order_id:
                transaction_payload["related_order"] = breakdown.order

            txn = Transaction.objects.create(**transaction_payload)
            account.current_balance = (account.current_balance or Decimal("0")) - breakdown.total
            account.save(update_fields=["current_balance"])

            breakdown.accounting_category = category
            breakdown.accounting_status = OrderCostBreakdown.ACCOUNTING_STATUS_POSTED
            breakdown.accounting_transaction = txn
            breakdown.accounting_posted_at = timezone.now()
            breakdown.save(
                update_fields=[
                    "accounting_category",
                    "accounting_status",
                    "accounting_transaction",
                    "accounting_posted_at",
                ]
            )

        order_type, order = _resolve_order_context_from_breakdown(breakdown)
        return JsonResponse(
            {
                "ok": True,
                "breakdown": _serialize_breakdown(breakdown),
                "transaction_id": txn.id,
                **_totals_payload(order, order_type),
            }
        )
    except ValueError as exc:
        return JsonResponse({"ok": False, "error": f"Fecha invalida: {exc}"}, status=400)
    except Exception as exc:  # pragma: no cover - guarded API error
        logger.exception("Error posting manual order cost to accounting")
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


@login_required
@user_passes_test(is_staff)
@require_POST
def api_update_shipping(request):
    """Update shipping cost for order/internal order."""
    try:
        data = json.loads(request.body)
        order_type = data.get("order_type", "internal")
        order_id = data.get("order_id")
        shipping_cost = _parse_decimal(data.get("shipping_cost"), default=Decimal("0"))

        order = _resolve_order(order_type, order_id)
        order.shipping_cost = shipping_cost
        order.save(update_fields=["shipping_cost"])

        return JsonResponse({"ok": True, "shipping_cost": str(shipping_cost)})
    except Exception as exc:  # pragma: no cover - guarded API error
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


@login_required
@user_passes_test(is_staff)
@require_POST
def api_update_discount(request):
    """Update discount amount for order/internal order."""
    try:
        data = json.loads(request.body)
        order_type = data.get("order_type", "internal")
        order_id = data.get("order_id")
        discount_amount = _parse_decimal(data.get("discount_amount"), default=Decimal("0"))

        if order_type == "internal":
            order = get_object_or_404(InternalOrder, id=order_id)
            order.discount_amount = discount_amount
            order.recalculate_totals()
        else:
            order = get_object_or_404(Order, id=order_id)
            order.discount_amount = discount_amount
            order.save(update_fields=["discount_amount"])

        return JsonResponse(
            {
                "ok": True,
                "discount_amount": str(discount_amount),
                "total_estimated": str(order.total_estimated) if order_type == "internal" else str(order.total),
            }
        )
    except Exception as exc:  # pragma: no cover - guarded API error
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)


@login_required
@user_passes_test(is_staff)
@require_POST
def api_update_variant_dimensions(request):
    """Legacy endpoint used by variants dashboard."""
    try:
        data = json.loads(request.body)
        variant_id = data.get("variant_id")
        variant = get_object_or_404(ProductVariant, id=variant_id)

        if "height_cm" in data:
            variant.height_cm = _parse_decimal(data.get("height_cm"), default=None)
        if "width_cm" in data:
            variant.width_cm = _parse_decimal(data.get("width_cm"), default=None)

        variant.save(update_fields=["height_cm", "width_cm"])
        return JsonResponse(
            {
                "ok": True,
                "id": variant.id,
                "height_cm": str(variant.height_cm) if variant.height_cm is not None else None,
                "width_cm": str(variant.width_cm) if variant.width_cm is not None else None,
            }
        )
    except (InvalidOperation, ValueError) as exc:
        return JsonResponse({"ok": False, "error": f"Valor invalido: {exc}"}, status=400)
    except Exception as exc:  # pragma: no cover - guarded API error
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
