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
            'payment_count': debt.payments.count()
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
