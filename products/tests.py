from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from contabilidad.models import Account, Transaction, TransactionCategory
from contabilidad.models_job_costing import FinancialStatus
from products.models_costs import CostType, OrderCostBreakdown
from products.models_internal_orders import InternalOrder


class ManualOrderCostsApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="staff",
            password="test1234",
            is_staff=True,
        )
        self.client.force_login(self.user)

        self.order = InternalOrder.objects.create(
            name="Pedido QA",
            created_by=self.user,
            total_estimated=Decimal("120000"),
            shipping_cost=Decimal("0"),
        )

        self.account = Account.objects.create(name="Caja QA", current_balance=Decimal("500000"))
        self.expense_category = TransactionCategory.objects.create(
            name="Produccion QA",
            transaction_type="egreso",
        )
        self.cost_type = CostType.objects.create(
            name="Descartonado",
            default_unit_price=Decimal("0"),
            accounting_category=self.expense_category,
        )

    def test_create_manual_cost_for_internal_order(self):
        response = self.client.post(
            reverse("api_create_order_cost"),
            data={
                "order_type": "internal",
                "order_id": self.order.id,
                "cost_type_id": self.cost_type.id,
                "description": "Descartonado frente",
                "total": "30000",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["breakdown"]["accounting_status"], "pending")
        self.assertEqual(Decimal(payload["total_costs"]), Decimal("30000"))

        breakdown = OrderCostBreakdown.objects.get(id=payload["breakdown"]["id"])
        self.assertEqual(breakdown.internal_order_id, self.order.id)
        self.assertTrue(breakdown.is_manual)
        self.assertEqual(breakdown.total, Decimal("30000"))

    def test_post_cost_to_accounting_creates_transaction_and_locks_breakdown(self):
        breakdown = OrderCostBreakdown.objects.create(
            internal_order=self.order,
            cost_type=self.cost_type,
            description="Descartonado frente",
            total=Decimal("30000"),
            is_manual=True,
            accounting_category=self.expense_category,
        )

        response = self.client.post(
            reverse("api_post_order_cost_to_accounting"),
            data={
                "breakdown_id": breakdown.id,
                "account_id": self.account.id,
                "date": "2026-02-10",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])

        breakdown.refresh_from_db()
        self.account.refresh_from_db()
        txn = Transaction.objects.get(id=payload["transaction_id"])

        self.assertEqual(breakdown.accounting_status, "posted")
        self.assertEqual(breakdown.accounting_transaction_id, txn.id)
        self.assertEqual(self.account.current_balance, Decimal("470000"))

        edit_response = self.client.post(
            reverse("api_update_order_cost"),
            data={
                "breakdown_id": breakdown.id,
                "description": "Intento de cambio",
            },
            content_type="application/json",
        )
        self.assertEqual(edit_response.status_code, 400)

    def test_internal_order_status_api_updates_financial_status(self):
        response = self.client.post(
            reverse("api_internal_order_update_status"),
            data={
                "order_id": self.order.id,
                "status": "material_purchased",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")

        self.order.refresh_from_db()
        fs = FinancialStatus.objects.get(internal_order=self.order)

        self.assertEqual(self.order.status, "material_purchased")
        self.assertEqual(fs.state, "material_comprado")

    def test_transition_financial_state_to_cobrado_syncs_internal_order_completed(self):
        fs = FinancialStatus.objects.get(internal_order=self.order)

        response = self.client.post(
            reverse("api_jc_transition"),
            data={
                "financial_status_id": fs.id,
                "new_state": "cobrado",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])

        fs.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(fs.state, "cobrado")
        self.assertEqual(self.order.status, "completed")
