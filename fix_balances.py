from contabilidad.models import Account, Transaction
from django.db.models import Sum

print("Actualizando saldos de cuentas...")
for account in Account.objects.all():
    ingresos = Transaction.objects.filter(
        account=account,
        category__transaction_type='ingreso'
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    egresos = Transaction.objects.filter(
        account=account,
        category__transaction_type='egreso'
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    nuevo_balance = ingresos - egresos
    
    print(f"  {account.name}:")
    print(f"    Ingresos: ${ingresos}")
    print(f"    Egresos: ${egresos}")
    print(f"    Balance anterior: ${account.current_balance}")
    print(f"    Balance nuevo: ${nuevo_balance}")
    
    account.current_balance = nuevo_balance
    account.save()

print("\n✅ Saldos actualizados correctamente!")
