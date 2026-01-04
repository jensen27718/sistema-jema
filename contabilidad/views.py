from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Sum
from .models import Account, Transaction, TransactionCategory, Provider, Debt, Payment

def is_staff(user):
    return user.is_staff or user.is_superuser

@login_required
@user_passes_test(is_staff)
def accounting_dashboard_view(request):
    from django.utils import timezone
    from datetime import datetime
    
    accounts = Account.objects.all()
    raw_transactions = Transaction.objects.select_related('account', 'category').order_by('-date', '-created_at')[:10]
    
    # Preparar datos de transacciones para el template (sin condicionales)
    recent_transactions = []
    for t in raw_transactions:
        # Determinar categoría y tipo
        if t.category:
            cat_name = t.category.name
            trans_type = t.category.transaction_type
        else:
            cat_name = "Transferencia"
            trans_type = "transferencia"
        
        # Agregar nombre de cliente si existe
        detail = cat_name
        if t.client_name:
            detail = f"{cat_name} - {t.client_name}"
        
        # Determinar color y signo
        if trans_type == 'ingreso':
            amount_class = "text-success"
            amount_sign = "+"
        else:
            amount_class = "text-danger"
            amount_sign = "-"
        
        recent_transactions.append({
            'date': t.date,
            'description': t.description,
            'detail': detail,
            'account_name': t.account.name,
            'amount': t.amount,
            'amount_class': amount_class,
            'amount_sign': amount_sign
        })
    
    # Calcular totales para la vista rápida
    total_balance = sum(acc.current_balance for acc in accounts)
    
    # Calcular ingresos y gastos del mes actual
    now = timezone.now()
    month_start = datetime(now.year, now.month, 1).date()
    
    monthly_income = Transaction.objects.filter(
        category__transaction_type='ingreso',
        date__gte=month_start
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    monthly_expenses = Transaction.objects.filter(
        category__transaction_type='egreso',
        date__gte=month_start
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    # Calcular ingresos mensuales por cuenta
    for account in accounts:
        account.monthly_income = Transaction.objects.filter(
            account=account,
            category__transaction_type='ingreso',
            date__gte=month_start
        ).aggregate(total=Sum('amount'))['total'] or 0
    
    context = {
        'accounts': accounts,
        'recent_transactions': recent_transactions,
        'total_balance': total_balance,
        'monthly_income': monthly_income,
        'monthly_expenses': monthly_expenses
    }
    return render(request, 'contabilidad/dashboard.html', context)

@login_required
@user_passes_test(is_staff)
def transaction_create_view(request):
    if request.method == 'POST':
        try:
            from decimal import Decimal
            
            amount = Decimal(request.POST.get('amount'))
            description = request.POST.get('description')
            account_id = request.POST.get('account_id')
            date = request.POST.get('date')
            
            account = get_object_or_404(Account, id=account_id)
            
            # Lógica de Transferencia
            transaction_type = request.POST.get('transaction_type')
            
            if transaction_type == 'transferencia':
                dest_account_id = request.POST.get('dest_account_id')
                dest_account = get_object_or_404(Account, id=dest_account_id)
                
                if account.id == dest_account.id:
                    messages.error(request, "La cuenta de origen y destino no pueden ser la misma.")
                    return redirect('accounting_transaction_create')

                if account.current_balance < amount:
                    messages.warning(request, "Advertencia: La cuenta de origen no tiene fondos suficientes.")

                # 1. Movimiento de Salida (Origen)
                Transaction.objects.create(
                    amount=amount,
                    description=f"Transferencia a {dest_account.name}: {description}",
                    account=account,
                    category=None,
                    date=date,
                    transfer_destination_account=dest_account
                )
                account.current_balance -= amount
                account.save()

                # 2. Movimiento de Entrada (Destino)
                Transaction.objects.create(
                    amount=amount,
                    description=f"Transferencia desde {account.name}: {description}",
                    account=dest_account,
                    category=None,
                    date=date
                )
                dest_account.current_balance += amount
                dest_account.save()
                
                messages.success(request, "Transferencia realizada exitosamente.")
                return redirect('accounting_dashboard')

            # Lógica Normal (Ingreso / Gasto)
            category_id = request.POST.get('category_id')
            category = get_object_or_404(TransactionCategory, id=category_id)
            
            # Lógica de Cliente / Proveedor
            from users.models import User
            from django.utils.crypto import get_random_string
            
            client_name = request.POST.get('client_name', '')
            user_to_link = None
            provider_to_link = None
            
            # Cliente (para Ingresos) - Solo existentes ahora
            client_id = request.POST.get('client_id')
            if client_id:
                user_to_link = User.objects.filter(id=client_id).first()
                if user_to_link:
                    client_name = user_to_link.get_full_name() or user_to_link.phone_number or user_to_link.email
            else:
                # Fallback para nombre manual si no se selecciona cliente pero se escribe algo
                manual_name = request.POST.get('client_name', '').strip()
                if manual_name:
                    client_name = manual_name

            # Proveedor (para Egresos)
            provider_id = request.POST.get('provider_id')
            if provider_id:
                provider_to_link = Provider.objects.filter(id=provider_id).first()
                if provider_to_link:
                    client_name = provider_to_link.name

            # Crear transacción y actualizar saldo en una transacción atómica
            from django.db import transaction as db_transaction
            
            with db_transaction.atomic():
                # Crear el movimiento
                new_transaction = Transaction.objects.create(
                    amount=amount,
                    description=description,
                    account=account,
                    category=category,
                    date=date,
                    client_name=client_name,
                    client=user_to_link,
                    provider=provider_to_link
                )
                
                # Actualizar saldo de cuenta
                old_balance = account.current_balance
                if category.transaction_type == 'ingreso':
                    account.current_balance += amount
                else:
                    account.current_balance -= amount
                account.save()
                
                # Log para debug
                print(f"[CONTABILIDAD] Movimiento #{new_transaction.id} creado")
                print(f"  - Cuenta: {account.name}")
                print(f"  - Tipo: {category.transaction_type}")
                print(f"  - Monto: ${amount}")
                print(f"  - Balance anterior: ${old_balance}")
                print(f"  - Balance nuevo: ${account.current_balance}")
            
            messages.success(request, f"✅ Movimiento registrado. Nuevo saldo: ${account.current_balance:,.2f}")
            return redirect('accounting_dashboard')
            
        except TransactionCategory.DoesNotExist:
            messages.error(request, "❌ Error: Categoría no encontrada.")
        except Account.DoesNotExist:
            messages.error(request, "❌ Error: Cuenta no encontrada.")
        except Exception as e:
            import traceback
            traceback.print_exc()
            messages.error(request, f"❌ Error al registrar: {str(e)}")
            
    # Contexto para el formulario
    from users.models import User
    users_list = User.objects.all().order_by('email')
    providers_list = Provider.objects.all().order_by('name')

    accounts = Account.objects.all()
    categories_income = TransactionCategory.objects.filter(transaction_type='ingreso')
    categories_expense = TransactionCategory.objects.filter(transaction_type='egreso')
    
    context = {
        'accounts': accounts,
        'categories_income': categories_income,
        'categories_expense': categories_expense,
        'users_list': users_list,
        'providers_list': providers_list
    }
    return render(request, 'contabilidad/form.html', context)

@login_required
@user_passes_test(is_staff)
def account_create_view(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        limit_amount = request.POST.get('limit_amount') or 0
        current_balance = request.POST.get('current_balance') or 0
        
        Account.objects.create(
            name=name,
            description=description,
            limit_amount=limit_amount,
            current_balance=current_balance
        )
        messages.success(request, f"Cuenta '{name}' creada exitosamente.")
        return redirect('accounting_dashboard')
        
    return render(request, 'contabilidad/account_form.html')

@login_required
@user_passes_test(is_staff)
def account_update_view(request, account_id):
    account = get_object_or_404(Account, id=account_id)
    
    if request.method == 'POST':
        account.name = request.POST.get('name')
        account.description = request.POST.get('description')
        account.limit_amount = float(request.POST.get('limit_amount') or 0)
        account.current_balance = float(request.POST.get('current_balance') or 0)
        account.save()
        
        messages.success(request, f"Cuenta '{account.name}' actualizada.")
        return redirect('accounting_dashboard')
        
    context = {'account': account}
    return render(request, 'contabilidad/account_form.html', context)

# --- CATEGORY CRUD ---

@login_required
@user_passes_test(is_staff)
def category_list_view(request):
    categories = TransactionCategory.objects.all().order_by('transaction_type', 'name')
    return render(request, 'contabilidad/category_list.html', {'categories': categories})

@login_required
@user_passes_test(is_staff)
def category_create_view(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        transaction_type = request.POST.get('transaction_type')
        
        TransactionCategory.objects.create(name=name, transaction_type=transaction_type)
        messages.success(request, f"Categoría '{name}' creada.")
        return redirect('accounting_category_list')

    return render(request, 'contabilidad/category_form.html')

@login_required
@user_passes_test(is_staff)
def category_update_view(request, category_id):
    category = get_object_or_404(TransactionCategory, id=category_id)
    
    if request.method == 'POST':
        category.name = request.POST.get('name')
        category.transaction_type = request.POST.get('transaction_type')
        category.save()
        messages.success(request, f"Categoría actualizada.")
        return redirect('accounting_category_list')

    context = {'category': category}
    return render(request, 'contabilidad/category_form.html', context)

@login_required
@user_passes_test(is_staff)
def category_delete_view(request, category_id):
    category = get_object_or_404(TransactionCategory, id=category_id)
    try:
        category.delete()
        messages.success(request, "Categoría eliminada.")
    except Exception as e:
        messages.error(request, "No se pudo eliminar (es posible que tenga movimientos asociados).")
    
    return redirect('accounting_category_list')

# --- PROVIDER CRUD ---

@login_required
@user_passes_test(is_staff)
def provider_list_view(request):
    providers = Provider.objects.all().order_by('name')
    return render(request, 'contabilidad/provider_list.html', {'providers': providers})

@login_required
@user_passes_test(is_staff)
def provider_create_view(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        phone = request.POST.get('phone')
        email = request.POST.get('email')
        
        Provider.objects.create(name=name, phone=phone, email=email)
        messages.success(request, f"Proveedor '{name}' creado.")
        return redirect('accounting_provider_list')

    return render(request, 'contabilidad/provider_form.html')

@login_required
@user_passes_test(is_staff)
def provider_update_view(request, provider_id):
    provider = get_object_or_404(Provider, id=provider_id)
    if request.method == 'POST':
        provider.name = request.POST.get('name')
        provider.phone = request.POST.get('phone')
        provider.email = request.POST.get('email')
        provider.save()
        messages.success(request, f"Proveedor actualizado.")
        return redirect('accounting_provider_list')

    context = {'provider': provider}
    return render(request, 'contabilidad/provider_form.html', context)

@login_required
@user_passes_test(is_staff)
def provider_delete_view(request, provider_id):
    provider = get_object_or_404(Provider, id=provider_id)
    try:
        provider.delete()
        messages.success(request, "Proveedor eliminado.")
    except:
        messages.error(request, "No se puede eliminar (tiene movimientos asociados).")
    return redirect('accounting_provider_list')
# ==========================
# DEBT MANAGEMENT VIEWS
# ==========================

@login_required
@user_passes_test(is_staff)
def debt_list_view(request):
    """Lista todas las deudas con información agregada"""
    debts = Debt.objects.select_related('provider').all().order_by('-date_created')
    
    # Agregar información calculada a cada deuda
    debts_with_info = []
    for debt in debts:
        pcount = debt.payments.count()
        ptext = "abono" if pcount == 1 else "abonos"
        debts_with_info.append({
            'id': debt.id,
            'provider': debt.provider,
            'description': debt.description,
            'total_amount': debt.total_amount,
            'total_paid': debt.get_total_paid(),
            'remaining': debt.get_remaining(),
            'progress': debt.get_progress_percentage(),
            'status': debt.status,
            'status_display': debt.get_status_display(),
            'date_created': debt.date_created,
            'payment_count': pcount,
            'payment_text': ptext,
        })
    
    context = {'debts': debts_with_info}
    return render(request, 'contabilidad/debts/list.html', context)


@login_required
@user_passes_test(is_staff)
def debt_create_view(request):
    """Crear una nueva deuda"""
    if request.method == 'POST':
        try:
            from decimal import Decimal
            
            provider_id = request.POST.get('provider_id')
            total_amount = Decimal(request.POST.get('total_amount'))
            description = request.POST.get('description')
            date_created = request.POST.get('date_created')
            
            provider = get_object_or_404(Provider, id=provider_id)
            
            Debt.objects.create(
                provider=provider,
                total_amount=total_amount,
                description=description,
                date_created=date_created
            )
            
            messages.success(request, f"✅ Deuda registrada: {provider.name} - ${total_amount:,.2f}")
            return redirect('accounting_debt_list')
            
        except Exception as e:
            messages.error(request, f"❌ Error al crear deuda: {str(e)}")
    
    providers = Provider.objects.all().order_by('name')
    context = {'providers': providers}
    return render(request, 'contabilidad/debts/form.html', context)


@login_required
@user_passes_test(is_staff)
def debt_detail_view(request, debt_id):
    """Vista detallada de una deuda con sus abonos"""
    debt = get_object_or_404(Debt, id=debt_id)
    payments = debt.payments.all().order_by('-payment_date')
    
    context = {
        'debt': debt,
        'payments': payments,
        'total_paid': debt.get_total_paid(),
        'remaining': debt.get_remaining(),
        'progress': debt.get_progress_percentage()
    }
    return render(request, 'contabilidad/debts/detail.html', context)


@login_required
@user_passes_test(is_staff)
def payment_create_view(request, debt_id):
    """Crear un abono a una deuda"""
    debt = get_object_or_404(Debt, id=debt_id)
    
    if request.method == 'POST':
        try:
            from decimal import Decimal
            
            amount = Decimal(request.POST.get('amount'))
            payment_date = request.POST.get('payment_date')
            notes = request.POST.get('notes', '')
            
            if amount <= 0:
                messages.error(request, "El monto debe ser mayor a cero.")
                return redirect('accounting_debt_detail', debt_id=debt_id)
            
            if amount > debt.get_remaining():
                messages.warning(request, f"El monto excede la deuda pendiente (${debt.get_remaining():,.2f})")
            
            Payment.objects.create(
                debt=debt,
                amount=amount,
                payment_date=payment_date,
                notes=notes
            )
            
            messages.success(request, f"✅ Abono registrado: ${amount:,.2f}. Pendiente: ${debt.get_remaining():,.2f}")
            return redirect('accounting_debt_detail', debt_id=debt_id)
            
        except Exception as e:
            messages.error(request, f"❌ Error al registrar abono: {str(e)}")
    
    return redirect('accounting_debt_detail', debt_id=debt_id)
