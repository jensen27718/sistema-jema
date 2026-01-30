from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Sum
from .models import Account, Transaction, TransactionCategory, Provider, Debt, Payment, Invoice, InvoiceItem, ShippingGuide, ShippingObservation

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
            'amount_sign': amount_sign,
            'id': t.id
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
def transaction_update_view(request, transaction_id):
    transaction = get_object_or_404(Transaction, id=transaction_id)
    account = transaction.account
    
    if request.method == 'POST':
        try:
            from decimal import Decimal
            from django.db import transaction as db_transaction
            
            old_amount = transaction.amount
            old_type = transaction.category.transaction_type if transaction.category else 'transferencia'
            
            new_amount = Decimal(request.POST.get('amount'))
            new_description = request.POST.get('description')
            new_date = request.POST.get('date')
            new_category_id = request.POST.get('category_id')
            
            # Por ahora no permitimos cambiar de cuenta o de transferencia a transacción normal vía edición simple
            # para evitar complejidad extrema en esta fase, pero sí permitimos cambiar categoría (del mismo tipo idealmente)
            new_category = get_object_or_404(TransactionCategory, id=new_category_id)
            new_type = new_category.transaction_type
            
            with db_transaction.atomic():
                # Revertir impacto anterior
                if old_type == 'ingreso':
                    account.current_balance -= old_amount
                elif old_type == 'egreso':
                    account.current_balance += old_amount
                
                # Aplicar nuevo impacto
                if new_type == 'ingreso':
                    account.current_balance += new_amount
                elif new_type == 'egreso':
                    account.current_balance -= new_amount
                
                account.save()
                
                # Actualizar transacción
                transaction.amount = new_amount
                transaction.description = new_description
                transaction.date = new_date
                transaction.category = new_category
                
                # Cliente/Proveedor
                client_id = request.POST.get('client_id')
                if client_id:
                    from users.models import User
                    transaction.client = User.objects.filter(id=client_id).first()
                
                provider_id = request.POST.get('provider_id')
                if provider_id:
                    transaction.provider = Provider.objects.filter(id=provider_id).first()
                
                transaction.save()
            
            messages.success(request, "Movimiento actualizado correctamente.")
            return redirect('accounting_dashboard')
            
        except Exception as e:
            messages.error(request, f"Error al actualizar: {str(e)}")
            
    # Contexto similar al create pero con la instancia
    from users.models import User
    users_list = User.objects.all().order_by('email')
    providers_list = Provider.objects.all().order_by('name')
    accounts = Account.objects.all()
    categories_income = TransactionCategory.objects.filter(transaction_type='ingreso')
    categories_expense = TransactionCategory.objects.filter(transaction_type='egreso')
    
    context = {
        'transaction': transaction,
        'accounts': accounts,
        'categories_income': categories_income,
        'categories_expense': categories_expense,
        'users_list': users_list,
        'providers_list': providers_list,
        'is_edit': True
    }
    return render(request, 'contabilidad/form.html', context)

@login_required
@user_passes_test(is_staff)
def transaction_delete_view(request, transaction_id):
    transaction = get_object_or_404(Transaction, id=transaction_id)
    account = transaction.account
    
    if request.method == 'POST':
        try:
            from django.db import transaction as db_transaction
            
            trans_type = transaction.category.transaction_type if transaction.category else 'transferencia'
            amount = transaction.amount
            
            with db_transaction.atomic():
                # Revertir impacto en el saldo
                if trans_type == 'ingreso':
                    account.current_balance -= amount
                elif trans_type == 'egreso':
                    account.current_balance += amount
                # Nota: Si es transferencia, requeriría revertir ambas cuentas (pendiente si se necesita)
                
                account.save()
                transaction.delete()
                
            messages.success(request, "Movimiento eliminado correctamente.")
            return redirect('accounting_dashboard')
        except Exception as e:
            messages.error(request, f"Error al eliminar: {str(e)}")
            
    return render(request, 'dashboard/categories/confirm_delete.html', {'object': transaction})

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
        from django.http import JsonResponse
        name = request.POST.get('name')
        phone = request.POST.get('phone')
        email = request.POST.get('email')
        
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest'
        
        if not name:
            if is_ajax:
                return JsonResponse({'success': False, 'error': 'El nombre es obligatorio.'}, status=400)
            messages.error(request, 'El nombre es obligatorio.')
        else:
            provider = Provider.objects.create(name=name, phone=phone, email=email)
            if is_ajax:
                return JsonResponse({
                    'success': True,
                    'provider': {
                        'id': provider.id,
                        'name': provider.name
                    }
                })
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


# ==========================
# TRANSACTIONS LIST WITH PAGINATION
# ==========================

@login_required
@user_passes_test(is_staff)
def transaction_list_view(request):
    """Lista todos los movimientos con paginacion y busqueda"""
    from django.core.paginator import Paginator
    from django.db.models import Q

    transactions = Transaction.objects.select_related('account', 'category', 'provider', 'client').order_by('-date', '-created_at')

    # Filtros
    search_query = request.GET.get('q', '').strip()
    account_filter = request.GET.get('account', '')
    type_filter = request.GET.get('type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if search_query:
        transactions = transactions.filter(
            Q(description__icontains=search_query) |
            Q(client_name__icontains=search_query) |
            Q(provider__name__icontains=search_query)
        )

    if account_filter:
        transactions = transactions.filter(account_id=account_filter)

    if type_filter:
        if type_filter == 'ingreso':
            transactions = transactions.filter(category__transaction_type='ingreso')
        elif type_filter == 'egreso':
            transactions = transactions.filter(category__transaction_type='egreso')
        elif type_filter == 'transferencia':
            transactions = transactions.filter(category__isnull=True)

    if date_from:
        transactions = transactions.filter(date__gte=date_from)

    if date_to:
        transactions = transactions.filter(date__lte=date_to)

    # Paginacion
    paginator = Paginator(transactions, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Preparar datos para el template
    transaction_list = []
    for t in page_obj:
        if t.category:
            cat_name = t.category.name
            trans_type = t.category.transaction_type
        else:
            cat_name = "Transferencia"
            trans_type = "transferencia"

        detail = cat_name
        if t.client_name:
            detail = f"{cat_name} - {t.client_name}"

        if trans_type == 'ingreso':
            amount_class = "text-success"
            amount_sign = "+"
            badge_class = "bg-success"
        elif trans_type == 'transferencia':
            amount_class = "text-primary"
            amount_sign = ""
            badge_class = "bg-primary"
        else:
            amount_class = "text-danger"
            amount_sign = "-"
            badge_class = "bg-danger"

        transaction_list.append({
            'id': t.id,
            'date': t.date,
            'description': t.description,
            'detail': detail,
            'account_name': t.account.name,
            'amount': t.amount,
            'amount_class': amount_class,
            'amount_sign': amount_sign,
            'trans_type': trans_type,
            'badge_class': badge_class,
        })

    accounts = Account.objects.all()

    context = {
        'transactions': transaction_list,
        'page_obj': page_obj,
        'accounts': accounts,
        'search_query': search_query,
        'account_filter': account_filter,
        'type_filter': type_filter,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'contabilidad/transaction_list.html', context)


@login_required
@user_passes_test(is_staff)
def account_detail_view(request, account_id):
    """Vista detallada de una cuenta con sus movimientos"""
    from django.core.paginator import Paginator
    from django.db.models import Q, Sum
    from django.utils import timezone
    from datetime import datetime

    account = get_object_or_404(Account, id=account_id)

    transactions = Transaction.objects.filter(account=account).select_related('category', 'provider', 'client').order_by('-date', '-created_at')

    # Filtros
    search_query = request.GET.get('q', '').strip()
    type_filter = request.GET.get('type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if search_query:
        transactions = transactions.filter(
            Q(description__icontains=search_query) |
            Q(client_name__icontains=search_query)
        )

    if type_filter:
        if type_filter == 'ingreso':
            transactions = transactions.filter(category__transaction_type='ingreso')
        elif type_filter == 'egreso':
            transactions = transactions.filter(category__transaction_type='egreso')
        elif type_filter == 'transferencia':
            transactions = transactions.filter(category__isnull=True)

    if date_from:
        transactions = transactions.filter(date__gte=date_from)

    if date_to:
        transactions = transactions.filter(date__lte=date_to)

    # Calcular totales del mes
    now = timezone.now()
    month_start = datetime(now.year, now.month, 1).date()

    monthly_income = Transaction.objects.filter(
        account=account,
        category__transaction_type='ingreso',
        date__gte=month_start
    ).aggregate(total=Sum('amount'))['total'] or 0

    monthly_expenses = Transaction.objects.filter(
        account=account,
        category__transaction_type='egreso',
        date__gte=month_start
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Paginacion
    paginator = Paginator(transactions, 25)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Preparar datos para el template
    transaction_list = []
    for t in page_obj:
        if t.category:
            cat_name = t.category.name
            trans_type = t.category.transaction_type
        else:
            cat_name = "Transferencia"
            trans_type = "transferencia"

        detail = cat_name
        if t.client_name:
            detail = f"{cat_name} - {t.client_name}"

        if trans_type == 'ingreso':
            amount_class = "text-success"
            amount_sign = "+"
            badge_class = "bg-success"
        elif trans_type == 'transferencia':
            amount_class = "text-primary"
            amount_sign = ""
            badge_class = "bg-primary"
        else:
            amount_class = "text-danger"
            amount_sign = "-"
            badge_class = "bg-danger"

        transaction_list.append({
            'id': t.id,
            'date': t.date,
            'description': t.description,
            'detail': detail,
            'amount': t.amount,
            'amount_class': amount_class,
            'amount_sign': amount_sign,
            'trans_type': trans_type,
            'badge_class': badge_class,
        })

    context = {
        'account': account,
        'transactions': transaction_list,
        'page_obj': page_obj,
        'monthly_income': monthly_income,
        'monthly_expenses': monthly_expenses,
        'search_query': search_query,
        'type_filter': type_filter,
        'date_from': date_from,
        'date_to': date_to,
    }
    return render(request, 'contabilidad/account_detail.html', context)


# ==========================
# INVOICE MANAGEMENT VIEWS
# ==========================

@login_required
@user_passes_test(is_staff)
def invoice_list_view(request):
    from django.core.paginator import Paginator
    from django.db.models import Q

    invoices = Invoice.objects.all()

    search_query = request.GET.get('q', '').strip()
    if search_query:
        invoices = invoices.filter(
            Q(number__icontains=search_query) |
            Q(client_name__icontains=search_query) |
            Q(notes__icontains=search_query)
        )

    paginator = Paginator(invoices, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'invoices': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
    }
    return render(request, 'contabilidad/invoices/list.html', context)


@login_required
@user_passes_test(is_staff)
def invoice_create_view(request):
    from decimal import Decimal, InvalidOperation
    from users.models import User

    if request.method == 'POST':
        try:
            from django.db import transaction as db_transaction

            client_id = request.POST.get('client_id')
            client_name = request.POST.get('client_name', '').strip()
            client_address = request.POST.get('client_address', '').strip()
            date = request.POST.get('date')
            notes = request.POST.get('notes', '').strip()
            discount = Decimal(request.POST.get('discount') or '0')

            client = None
            if client_id:
                client = User.objects.filter(id=client_id, role=User.Role.CUSTOMER).first()
                if client and not client_name:
                    client_name = client.get_full_name() or client.username

            # Collect items
            descriptions = request.POST.getlist('item_description')
            quantities = request.POST.getlist('item_quantity')
            prices = request.POST.getlist('item_price')

            if not descriptions or not any(d.strip() for d in descriptions):
                messages.error(request, "Debe agregar al menos un item a la factura.")
                raise ValueError("No items")

            with db_transaction.atomic():
                invoice = Invoice.objects.create(
                    number=Invoice.get_next_number(),
                    client=client,
                    client_name=client_name,
                    client_address=client_address,
                    date=date,
                    notes=notes,
                    discount=discount,
                )

                for desc, qty, price in zip(descriptions, quantities, prices):
                    if desc.strip():
                        InvoiceItem.objects.create(
                            invoice=invoice,
                            description=desc.strip(),
                            quantity=Decimal(qty or '1'),
                            unit_price=Decimal(price or '0'),
                        )

            messages.success(request, f"Factura {invoice.number} creada exitosamente.")
            return redirect('invoice_detail', invoice_id=invoice.id)

        except (ValueError, InvalidOperation) as e:
            if str(e) != "No items":
                messages.error(request, f"Error en los datos ingresados: {str(e)}")
        except Exception as e:
            messages.error(request, f"Error al crear factura: {str(e)}")

    customers = User.objects.filter(role=User.Role.CUSTOMER).order_by('first_name', 'last_name')
    next_number = Invoice.get_next_number()

    context = {
        'customers': customers,
        'next_number': next_number,
    }
    return render(request, 'contabilidad/invoices/form.html', context)


@login_required
@user_passes_test(is_staff)
def invoice_detail_view(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    items = invoice.items.all()

    context = {
        'invoice': invoice,
        'items': items,
        'subtotal': invoice.get_subtotal(),
        'total': invoice.get_total(),
    }
    return render(request, 'contabilidad/invoices/detail.html', context)


@login_required
@user_passes_test(is_staff)
def invoice_delete_view(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    if request.method == 'POST':
        number = invoice.number
        invoice.delete()
        messages.success(request, f"Factura {number} eliminada.")
        return redirect('invoice_list')
    return render(request, 'dashboard/categories/confirm_delete.html', {'object': invoice})


@login_required
@user_passes_test(is_staff)
def api_client_address(request, client_id):
    from django.http import JsonResponse
    from users.models import User

    try:
        client = User.objects.get(id=client_id, role=User.Role.CUSTOMER)
        return JsonResponse({
            'success': True,
            'address': client.address or '',
            'name': client.get_full_name() or client.username,
        })
    except User.DoesNotExist:
        return JsonResponse({'success': False}, status=404)


# ==========================
# SHIPPING GUIDE VIEWS
# ==========================

@login_required
@user_passes_test(is_staff)
def guide_list_view(request):
    from django.core.paginator import Paginator
    from django.db.models import Q

    guides = ShippingGuide.objects.all()

    search_query = request.GET.get('q', '').strip()
    if search_query:
        guides = guides.filter(
            Q(number__icontains=search_query) |
            Q(sender_name__icontains=search_query) |
            Q(sender_lastname__icontains=search_query) |
            Q(recipient_name__icontains=search_query) |
            Q(recipient_lastname__icontains=search_query) |
            Q(recipient_cedula__icontains=search_query) |
            Q(recipient_city__icontains=search_query)
        )

    paginator = Paginator(guides, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'guides': page_obj,
        'page_obj': page_obj,
        'search_query': search_query,
    }
    return render(request, 'contabilidad/guides/list.html', context)


@login_required
@user_passes_test(is_staff)
def guide_create_view(request):
    from decimal import Decimal, InvalidOperation
    from users.models import User

    if request.method == 'POST':
        try:
            guide = ShippingGuide(
                number=ShippingGuide.get_next_number(),
                sender_name=request.POST.get('sender_name', ''),
                sender_lastname=request.POST.get('sender_lastname', ''),
                sender_cedula=request.POST.get('sender_cedula', ''),
                sender_phone=request.POST.get('sender_phone', ''),
                sender_department=request.POST.get('sender_department', ''),
                sender_city=request.POST.get('sender_city', ''),
                sender_address=request.POST.get('sender_address', ''),
                recipient_name=request.POST.get('recipient_name', ''),
                recipient_lastname=request.POST.get('recipient_lastname', ''),
                recipient_cedula=request.POST.get('recipient_cedula', ''),
                recipient_phone=request.POST.get('recipient_phone', ''),
                recipient_department=request.POST.get('recipient_department', ''),
                recipient_city=request.POST.get('recipient_city', ''),
                recipient_address=request.POST.get('recipient_address', ''),
                observation=request.POST.get('observation', ''),
            )

            client_id = request.POST.get('client_id')
            if client_id:
                guide.client = User.objects.filter(id=client_id).first()

            try:
                guide.collection_value = Decimal(request.POST.get('collection_value') or '0')
            except InvalidOperation:
                guide.collection_value = Decimal('0')

            guide.save()
            messages.success(request, f"Guía {guide.number} creada exitosamente.")
            return redirect('guide_list')

        except Exception as e:
            messages.error(request, f"Error al crear guía: {str(e)}")

    # Pre-llenar remitente con datos de la última guía
    last_guide = ShippingGuide.objects.first()
    observations = ShippingObservation.objects.all()

    context = {
        'last_guide': last_guide,
        'observations': observations,
        'next_number': ShippingGuide.get_next_number(),
    }
    return render(request, 'contabilidad/guides/form.html', context)


@login_required
@user_passes_test(is_staff)
def guide_detail_view(request, guide_id):
    guide = get_object_or_404(ShippingGuide, id=guide_id)
    return render(request, 'contabilidad/guides/detail.html', {'guide': guide})


@login_required
@user_passes_test(is_staff)
def guide_delete_view(request, guide_id):
    guide = get_object_or_404(ShippingGuide, id=guide_id)
    if request.method == 'POST':
        number = guide.number
        guide.delete()
        messages.success(request, f"Guía {number} eliminada.")
        return redirect('guide_list')
    return render(request, 'dashboard/categories/confirm_delete.html', {'object': guide})


@login_required
@user_passes_test(is_staff)
def guide_print_view(request):
    ids_param = request.GET.get('ids', '')
    if ids_param:
        ids = [int(x) for x in ids_param.split(',') if x.strip().isdigit()]
        guides = ShippingGuide.objects.filter(id__in=ids)
    else:
        guides = ShippingGuide.objects.none()

    return render(request, 'contabilidad/guides/print.html', {'guides': guides})


@login_required
@user_passes_test(is_staff)
def api_guide_client_data(request, client_id):
    from django.http import JsonResponse
    from users.models import User

    try:
        client = User.objects.get(id=client_id)
        return JsonResponse({
            'success': True,
            'first_name': client.first_name or '',
            'last_name': client.last_name or '',
            'cedula': client.cedula or '',
            'phone': client.phone_number or '',
            'address': client.address or '',
        })
    except User.DoesNotExist:
        return JsonResponse({'success': False}, status=404)


@login_required
@user_passes_test(is_staff)
def api_observations(request):
    from django.http import JsonResponse

    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        if text:
            obs, created = ShippingObservation.objects.get_or_create(text=text)
            return JsonResponse({'success': True, 'id': obs.id, 'text': obs.text, 'created': created})
        return JsonResponse({'success': False, 'error': 'Texto vacío'}, status=400)

    observations = list(ShippingObservation.objects.values('id', 'text'))
    return JsonResponse({'observations': observations})


@login_required
@user_passes_test(is_staff)
def api_search_clients(request):
    from django.http import JsonResponse
    from django.db.models import Q
    from users.models import User

    q = request.GET.get('q', '').strip()
    if len(q) < 2:
        return JsonResponse({'clients': []})

    clients = User.objects.filter(
        Q(first_name__icontains=q) |
        Q(last_name__icontains=q) |
        Q(cedula__icontains=q) |
        Q(phone_number__icontains=q) |
        Q(username__icontains=q)
    )[:10]

    results = [{
        'id': c.id,
        'first_name': c.first_name or '',
        'last_name': c.last_name or '',
        'cedula': c.cedula or '',
        'phone': c.phone_number or '',
        'address': c.address or '',
        'label': f"{c.first_name} {c.last_name}".strip() or c.username,
    } for c in clients]

    return JsonResponse({'clients': results})
