"""
context_processor.py

This module is used to register context processor`
"""

from employee.models import Employee
from payroll.models import tax_models as models
from payroll.models.models import Deduction


def default_currency(request):
    """
    This method will return the currency
    """
    if models.PayrollSettings.objects.first() is None:
        settings = models.PayrollSettings()
        # Default currency symbol and position for new installations
        settings.currency_symbol = "₱"
        try:
            settings.position = "prefix"
        except Exception:
            # In case the field is not present in this model version, ignore
            pass
        settings.save()
    symbol = models.PayrollSettings.objects.first().currency_symbol
    position = models.PayrollSettings.objects.first().position
    return {
        "currency": request.session.get("currency", symbol),
        "position": request.session.get("position", position),
    }


def host(request):
    """
    This method will return the host
    """
    protocol = "https" if request.is_secure() else "http"
    return {"host": request.get_host(), "protocol": protocol}


def get_deductions(request):
    """
    This method used to return the deduction
    """
    deductions = Deduction.objects.filter(
        only_show_under_employee=False, employer_rate__gt=0
    )
    return {"get_deductions": deductions}


def get_active_employees(request):
    """
    This method used to return the deduction
    """
    employees = Employee.objects.filter(
        is_active=True, contract_set__isnull=False, payslip__isnull=False
    ).distinct()
    return {"get_active_employees": employees}
