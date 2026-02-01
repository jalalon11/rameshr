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


def get_attendance_late_minutes(attendance) -> float:
    """
    Calculate late arrival minutes from an attendance record.
    
    Late = Clock-in time - Shift start time
    
    This calculates the ACTUAL late arrival time, which is different from
    undertime (which only considers total worked hours vs minimum required).
    
    Example:
        - Shift starts at 8:00 AM
        - Employee clocks in at 8:04 AM
        - Late minutes = 4 (even if they work 8 full hours)
    
    Args:
        attendance: Attendance model instance
    
    Returns:
        Late minutes (0 if on time or early)
    """
    from datetime import datetime
    from base.models import EmployeeShiftSchedule
    
    # Need both clock-in time and date
    if not attendance.attendance_clock_in or not attendance.attendance_clock_in_date:
        return 0.0
    
    # Get the shift for this attendance
    shift = attendance.shift_id
    if not shift:
        return 0.0
    
    # Get the day of week for the attendance date
    day_name = attendance.attendance_date.strftime("%A").lower()
    
    # Find the shift schedule for this day
    try:
        schedule = EmployeeShiftSchedule.objects.filter(
            shift_id=shift,
            day__day=day_name
        ).first()
        
        if not schedule or not schedule.start_time:
            return 0.0
        
        shift_start = schedule.start_time
        clock_in = attendance.attendance_clock_in
        
        # Combine with date for proper comparison
        clock_in_dt = datetime.combine(attendance.attendance_clock_in_date, clock_in)
        shift_start_dt = datetime.combine(attendance.attendance_clock_in_date, shift_start)
        
        # Calculate late minutes
        if clock_in_dt > shift_start_dt:
            late_seconds = (clock_in_dt - shift_start_dt).total_seconds()
            return late_seconds / 60
        
        return 0.0
        
    except Exception:
        return 0.0


def is_half_day_arrival(attendance) -> bool:
    """
    Determine if an attendance record represents a "Half Day" arrival.

    Half Day = Clock-in is after the shift midpoint (second half of shift).

    For an 8AM-5PM shift (8 hours with 1 hour lunch at 12 PM):
    - Shift working hours: 4 hours AM (8-12) + 4 hours PM (1-5)
    - Midpoint: 12:00 PM (end of first half)
    - Second half starts: 1:00 PM (after lunch)
    - Clock-in at/after 1:00 PM = Half Day
    - Clock-in before 1:00 PM = Late (but not Half Day)

    Args:
        attendance: Attendance model instance

    Returns:
        True if clock-in is after shift midpoint (Half Day), False otherwise
    """
    from datetime import datetime, timedelta

    from base.models import EmployeeShiftSchedule

    # Need clock-in time and date
    if not attendance.attendance_clock_in or not attendance.attendance_clock_in_date:
        return False

    # Get the shift for this attendance
    shift = attendance.shift_id
    if not shift:
        return False

    # Get the day of week for the attendance date
    day_name = attendance.attendance_date.strftime("%A").lower()

    try:
        schedule = EmployeeShiftSchedule.objects.filter(
            shift_id=shift, day__day=day_name
        ).first()

        if not schedule or not schedule.start_time or not schedule.end_time:
            return False

        shift_start = schedule.start_time
        shift_end = schedule.end_time
        clock_in = attendance.attendance_clock_in

        # Total shift span in minutes (e.g., 8AM-5PM = 9 hours = 540 min)
        start_dt = datetime.combine(attendance.attendance_date, shift_start)
        if schedule.is_night_shift or shift_end < shift_start:
            end_dt = datetime.combine(
                attendance.attendance_date + timedelta(days=1), shift_end
            )
        else:
            end_dt = datetime.combine(attendance.attendance_date, shift_end)

        total_shift_span_minutes = (end_dt - start_dt).total_seconds() / 60

        # Standard lunch break duration (1 hour)
        LUNCH_BREAK_MINUTES = 60

        # Working hours = total shift span - lunch break
        # For 8AM-5PM: 9 hours - 1 hour lunch = 8 working hours
        working_minutes = total_shift_span_minutes - LUNCH_BREAK_MINUTES

        # First half of working day (half of working hours, not total span)
        # For 8 working hours: first half = 4 hours = 240 minutes
        first_half_minutes = working_minutes / 2

        # Second half starts after: first half + lunch break
        # For 8AM start: 8AM + 4 hours (first half) + 1 hour (lunch) = 1PM
        # This means: shift_start + first_half + lunch = second_half_start
        second_half_start_dt = start_dt + timedelta(
            minutes=first_half_minutes + LUNCH_BREAK_MINUTES
        )

        # Compare clock-in time with second half start
        clock_in_dt = datetime.combine(attendance.attendance_clock_in_date, clock_in)

        # If clock-in is at or after the second half start, it's Half Day
        return clock_in_dt >= second_half_start_dt

    except Exception:
        return False


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
    Supports PARTIAL deductions when balance is insufficient.
    
    This function:
    1. Calculates the leave credits to deduct
    2. Deducts from the employee's leave allocation (partial if insufficient)
    3. Records the deduction with covered vs uncovered time
    
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
        - credits_requested: float (original request)
        - credits_deducted: float (what was actually deducted)
        - is_partial: bool (True if partial deduction)
        - covered_minutes: float (minutes covered by leave)
        - uncovered_minutes: float (minutes remaining as LOP)
        - balance_before: float
        - balance_after: float
        - record: UndertimeLeaveDeduction instance
    """
    AvailableLeave = apps.get_model("leave", "AvailableLeave")
    UndertimeLeaveDeduction = apps.get_model("leave", "UndertimeLeaveDeduction")
    
    # Calculate credit amount requested
    credits_requested = calculate_credits(undertime_minutes)
    if credits_requested <= 0:
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
    
    # Perform the deduction (may be partial)
    result = available.deduct_credits(credits_requested)
    
    if not result["success"]:
        return result
    
    # Calculate covered vs uncovered minutes
    credits_deducted = result["amount_deducted"]
    is_partial = result["is_partial"]
    
    # Convert credits back to minutes (credits * 480 = minutes)
    covered_minutes = round(credits_deducted * MINUTES_PER_CREDIT, 1)
    uncovered_minutes = round(undertime_minutes - covered_minutes, 1)
    
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
        undertime_covered_minutes=covered_minutes,
        undertime_uncovered_minutes=uncovered_minutes,
        credits_requested=credits_requested,
        credits_deducted=credits_deducted,
        is_partial_deduction=is_partial,
        balance_before=result["balance_before"],
        balance_after=result["balance_after"],
        processed_by=processed_by,
        notes=notes
    )
    
    return {
        "success": True,
        "credits_requested": credits_requested,
        "credits_deducted": credits_deducted,
        "is_partial": is_partial,
        "covered_minutes": covered_minutes,
        "uncovered_minutes": uncovered_minutes,
        "balance_before": result["balance_before"],
        "balance_after": result["balance_after"],
        "record": record
    }


def get_employee_leave_types_for_deduction(employee):
    """
    Get leave types available for undertime deduction for an employee.
    
    Returns all leave types that the employee has an allocation for.
    Since partial deductions are now supported, any leave type with
    available balance can be used (even if balance is low).
    
    Args:
        employee: Employee model instance
    
    Returns:
        QuerySet of LeaveType instances
    """
    LeaveType = apps.get_model("leave", "LeaveType")
    AvailableLeave = apps.get_model("leave", "AvailableLeave")
    
    # Get leave type IDs that the employee has allocations for
    # Include all types with positive balance
    allocated_type_ids = AvailableLeave.objects.filter(
        employee_id=employee,
        total_leave_days__gt=0  # Only show types with available credits
    ).values_list("leave_type_id", flat=True)
    
    return LeaveType.objects.filter(id__in=allocated_type_ids)

