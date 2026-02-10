import os
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from products.models_internal_orders import InternalOrder, InternalOrderItem
from products.models_costs import OrderCostBreakdown, CostType
from products.models import Product, ProductVariant

def verify():
    print("Starting verification...")
    
    # 1. Create a dummy order
    order = InternalOrder.objects.create(name="Test Order Verification")
    print(f"Created order #{order.id}")
    
    # 2. Add an item
    # Assuming we have at least one variant
    variant = ProductVariant.objects.first()
    if not variant:
        print("No variant found to test.")
        return
        
    item = InternalOrderItem.objects.create(
        order=order,
        variant=variant,
        quantity=2,
        unit_price=Decimal("1000")
    )
    print(f"Added item: 2 x 1000 = 2000")
    
    order.recalculate_totals()
    print(f"Total after item: {order.total_estimated} (Expected: 2000)")
    
    # 3. Add an expense
    cost_type = CostType.objects.first()
    expense = OrderCostBreakdown.objects.create(
        internal_order=order,
        cost_type=cost_type,
        description="Manual Expense",
        total=Decimal("500")
    )
    print("Added expense of 500")
    
    order.recalculate_totals()
    print(f"Total after expense: {order.total_estimated} (Expected: 1500)")
    
    # 4. Add a discount
    order.discount_amount = Decimal("200")
    order.recalculate_totals()
    print(f"Total after discount of 200: {order.total_estimated} (Expected: 1300)")
    
    # Cleaning up
    order.delete()
    print("Verification cleanup done.")

if __name__ == "__main__":
    verify()
