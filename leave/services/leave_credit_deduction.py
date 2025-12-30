"""
leave_credit_deduction.py

Service module for automatic leave credit deduction based on undertime.

This module provides functions to calculate and process leave credit
deductions when employees have undertime (late arrival, early departure,
or absence).

Calculation Formula (based on 8-hour / 480-minute workday):
- 1 minute ≈ 0.002 leave credits (1/480)
- 1 hour = 0.125 leave credits (1/8)
- 8 hours = 1.0 leave credit
"""

from django.apps import apps
from django.utils import timezone


# Standard 8-hour workday = 480 minutes = 1 leave credit
MINUTES_PER_CREDIT = 480


def calculate_credits(undertime_minutes: float) -> float:
    """
    Calculate leave credits to deduct based on undertime.
    
    Formula: credits = undertime_minutes / 480
    
    Examples:
        1 min   → 0.002 credits
        30 min  → 0.063 credits
        1 hour  → 0.125 credits
        2 hours → 0.250 credits
        8 hours → 1.000 credits
    
    Args:
        undertime_minutes: Total undertime in minutes
    
    Returns:
        Fractional leave credit amount (rounded to 3 decimal places)
    """
    if undertime_minutes <= 0:
        return 0.0
    return round(undertime_minutes / MINUTES_PER_CREDIT, 3)


def get_attendance_undertime(attendance) -> float:
    """
    Calculate undertime in minutes from an attendance record.
    
    Undertime = Required hours - Actual worked hours
    
    Args:
        attendance: Attendance model instance
    
    Returns:
        Undertime in minutes (0 if no undertime, i.e., worked enough)
    """
    from attendance.methods.utils import strtime_seconds
    
    min_hour_seconds = strtime_seconds(attendance.minimum_hour)
    worked_seconds = attendance.at_work_second
    
    if worked_seconds >= min_hour_seconds:
        return 0.0
    
    undertime_seconds = min_hour_seconds - worked_seconds
    return undertime_seconds / 60


def process_deduction(
    employee,
    leave_type,
    undertime_minutes: float,
    attendance=None,
    processed_by=None,
    notes: str = ""
) -> dict:
    """
    Process leave credit deduction for an employee.
    
    This function:
    1. Calculates the leave credits to deduct
    2. Deducts from the employee's leave allocation
    3. Records the deduction in UndertimeLeaveDeduction for audit
    
    Args:
        employee: Employee to deduct from
        leave_type: LeaveType to use for deduction (selected by HR)
        undertime_minutes: Amount of undertime in minutes
        attendance: Optional linked attendance record
        processed_by: HR employee processing this deduction
        notes: Optional notes about the deduction
    
    Returns:
        dict with result details:
        - success: bool
        - error: str (if failed)
        - amount_deducted: float (if successful)
        - balance_before: float
        - balance_after: float
        - record: UndertimeLeaveDeduction instance
    """
    AvailableLeave = apps.get_model("leave", "AvailableLeave")
    UndertimeLeaveDeduction = apps.get_model("leave", "UndertimeLeaveDeduction")
    
    # Calculate credit amount to deduct
    credits = calculate_credits(undertime_minutes)
    if credits <= 0:
        return {"success": False, "error": "No deduction needed (undertime is zero)"}
    
    # Get employee's leave allocation for the selected leave type
    try:
        available = AvailableLeave.objects.get(
            employee_id=employee,
            leave_type_id=leave_type
        )
    except AvailableLeave.DoesNotExist:
        return {
            "success": False,
            "error": f"Employee {employee} has no allocation for {leave_type.name}"
        }
    
    # Check if leave type allows negative balance (has reset or carryforward)
    if not available.can_go_negative() and available.total_leave_days < credits:
        return {
            "success": False,
            "error": f"Insufficient leave credits. Available: {available.total_leave_days:.3f}, Required: {credits:.3f}. This leave type doesn't allow negative balance."
        }
    
    # Perform the deduction
    result = available.deduct_credits(credits)
    
    if not result["success"]:
        return result
    
    # Determine the deduction date
    if attendance:
        deduction_date = attendance.attendance_date
    else:
        deduction_date = timezone.now().date()
    
    # Record the deduction for audit trail
    record = UndertimeLeaveDeduction.objects.create(
        employee_id=employee,
        leave_type_id=leave_type,
        attendance_id=attendance,
        deduction_date=deduction_date,
        undertime_minutes=undertime_minutes,
        credits_deducted=credits,
        balance_before=result["balance_before"],
        balance_after=result["balance_after"],
        processed_by=processed_by,
        notes=notes
    )
    
    result["record"] = record
    result["credits_deducted"] = credits
    return result


def get_employee_leave_types_for_deduction(employee):
    """
    Get leave types available for undertime deduction for an employee.
    
    Only returns leave types that:
    1. The employee has an allocation for
    2. Allow negative balance (have reset or carryforward enabled)
    
    Args:
        employee: Employee model instance
    
    Returns:
        QuerySet of LeaveType instances
    """
    LeaveType = apps.get_model("leave", "LeaveType")
    AvailableLeave = apps.get_model("leave", "AvailableLeave")
    
    # Get leave type IDs that the employee has allocations for
    allocated_type_ids = AvailableLeave.objects.filter(
        employee_id=employee
    ).values_list("leave_type_id", flat=True)
    
    # Filter to only leave types that support negative balance
    # (reset=True OR carryforward_type != "no carryforward")
    from django.db.models import Q
    return LeaveType.objects.filter(
        id__in=allocated_type_ids
    ).filter(
        Q(reset=True) | ~Q(carryforward_type="no carryforward")
    )
