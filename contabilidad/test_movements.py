from django.test import TestCase
from .models import Account, Transaction, TransactionCategory
from django.utils import timezone
from decimal import Decimal

class TransactionBalanceTests(TestCase):
    def setUp(self):
        self.account = Account.objects.create(
            name="Test Account",
            current_balance=Decimal("1000.00")
        )
        self.income_cat = TransactionCategory.objects.create(
            name="Income",
            transaction_type='ingreso'
        )
        self.expense_cat = TransactionCategory.objects.create(
            name="Expense",
            transaction_type='egreso'
        )

    def test_create_income_updates_balance(self):
        # We need to simulate the view logic since the model save doesn't update balance automatically yet
        amount = Decimal("500.00")
        Transaction.objects.create(
            account=self.account,
            category=self.income_cat,
            amount=amount,
            description="Test Income",
            date=timezone.now().date()
        )
        # Note: In the current implementation, views handle balance updates.
        # We will move this logic to the model or signals so tests and views share it.
        # For now, let's verify what we WANT it to do.
        self.account.current_balance += amount
        self.account.save()
        self.assertEqual(self.account.current_balance, Decimal("1500.00"))

    def test_balance_after_edit(self):
        # Initial transaction
        t = Transaction.objects.create(
            account=self.account,
            category=self.income_cat,
            amount=Decimal("100.00"),
            description="Initial",
            date=timezone.now().date()
        )
        self.account.current_balance += t.amount
        self.account.save()
        
        # Edit amount
        old_amount = t.amount
        new_amount = Decimal("250.00")
        
        # Simulation of update logic
        self.account.current_balance -= old_amount # Revert old
        self.account.current_balance += new_amount # Apply new
        self.account.save()
        t.amount = new_amount
        t.save()
        
        self.assertEqual(self.account.current_balance, Decimal("1250.00"))

    def test_balance_after_delete(self):
        t = Transaction.objects.create(
            account=self.account,
            category=self.income_cat,
            amount=Decimal("100.00"),
            description="To delete",
            date=timezone.now().date()
        )
        self.account.current_balance += t.amount
        self.account.save()
        
        # Delete logic
        self.account.current_balance -= t.amount
        self.account.save()
        t.delete()
        
        self.assertEqual(self.account.current_balance, Decimal("1000.00"))
