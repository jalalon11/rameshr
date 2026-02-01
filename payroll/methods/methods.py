"""
methods.py

Payroll related module to write custom calculation methods
"""

import calendar
from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.core.paginator import Paginator
from django.db.models import F, Q

# from attendance.models import Attendance
from base.methods import (
    get_company_leave_dates,
    get_date_range,
    get_holiday_dates,
    get_pagination,
    get_working_days,
)
from base.models import CompanyLeaves, Holidays, EmployeeShiftSchedule
from horilla.methods import get_horilla_model_class
from payroll.models.models import Contract, Deduction, Payslip


def get_employee_working_days(employee, start_date, end_date):
    """
    Get working days for a specific employee based on their shift schedule.
    
    This function calculates working days by:
    1. Getting the employee's assigned shift schedule
    2. Finding which days of the week the employee is scheduled to work
    3. Counting only those scheduled days within the period
    4. Excluding holidays that fall on scheduled work days
    
    Args:
        employee: Employee model instance
        start_date (date): The start date of the period
        end_date (date): The end date of the period
    
    Returns:
        dict: {
            'total_working_days': int,
            'working_days_on': list of dates,
            'company_leave_dates': list of holiday dates
        }
    """
    # Get holiday/company leave dates
    holiday_dates = get_holiday_dates(start_date, end_date)
    company_leave_dates = (
        list(
            set(
                get_company_leave_dates(start_date.year)
                + get_company_leave_dates(end_date.year)
            )
        )
        + holiday_dates
    )
    company_leave_dates = [
        d for d in list(set(company_leave_dates))
        if start_date <= d <= end_date
    ]
    
    # Try to get employee's shift schedule
    scheduled_day_names = None
    try:
        # Get employee's shift from work info
        if hasattr(employee, 'employee_work_info') and employee.employee_work_info:
            shift = employee.employee_work_info.shift_id
            if shift:
                # Get the shift schedule entries (which days this shift works)
                schedules = EmployeeShiftSchedule.objects.filter(shift_id=shift)
                if schedules.exists():
                    # Get day names (lowercase) that this shift works
                    scheduled_day_names = [
                        schedule.day.day.lower() for schedule in schedules
                    ]
    except Exception:
        scheduled_day_names = None
    
    # Generate all dates in the range
    date_range = get_date_range(start_date, end_date)
    
    # Filter to only scheduled work days if we have shift info
    if scheduled_day_names:
        # Map Python weekday() to day names
        weekday_map = {
            0: 'monday',
            1: 'tuesday',
            2: 'wednesday',
            3: 'thursday',
            4: 'friday',
            5: 'saturday',
            6: 'sunday'
        }
        
        # Filter dates to only include scheduled work days
        scheduled_dates = [
            d for d in date_range
            if weekday_map.get(d.weekday()) in scheduled_day_names
        ]
    else:
        # Fallback: use all dates if no shift schedule found
        scheduled_dates = date_range
    
    # Exclude holidays from scheduled work days
    working_days = [d for d in scheduled_dates if d not in company_leave_dates]
    total_working_days = len(working_days)
    
    return {
        'total_working_days': total_working_days,
        'working_days_on': working_days,
        'company_leave_dates': company_leave_dates,
    }


def get_total_days(start_date, end_date):
    """
    Calculates the total number of days in a given period.

    Args:
        start_date (date): The start date of the period.

        end_date (date): The end date of the period.
    Returns:
        int: The total number of days in the period, including the end date.

    Example:
        start_date = date(2023, 1, 1)
        end_date = date(2023, 1, 10)
        days_on_period = get_total_days(start_date, end_date)
    """
    delta = end_date - start_date
    total_days = delta.days + 1  # Add 1 to include the end date itself
    return total_days


def get_leaves(employee, start_date, end_date):
    """
    This method is used to return all the leaves taken by the employee
    between the period.

    Args:
        employee (obj): Employee model instance
        start_date (obj): the start date from the data needed
        end_date (obj): the end date till the date needed
    """
    if apps.is_installed("leave"):
        approved_leaves = employee.leaverequest_set.filter(status="approved")
    else:
        approved_leaves = None
    paid_leave = 0
    unpaid_leave = 0
    paid_half = 0
    unpaid_half = 0
    paid_leave_dates = []
    unpaid_leave_dates = []
    company_leave_dates = get_working_days(start_date, end_date)["company_leave_dates"]

    if approved_leaves and approved_leaves.exists():
        for instance in approved_leaves:
            if instance.leave_type_id.payment == "paid":
                # if the taken leave is paid
                # for the start date
                all_the_paid_leave_taken_dates = instance.requested_dates()
                paid_leave_dates = paid_leave_dates + [
                    date
                    for date in all_the_paid_leave_taken_dates
                    if start_date <= date <= end_date
                ]
            else:
                # if the taken leave is unpaid
                # for the start date
                all_unpaid_leave_taken_dates = instance.requested_dates()
                unpaid_leave_dates = unpaid_leave_dates + [
                    date
                    for date in all_unpaid_leave_taken_dates
                    if start_date <= date <= end_date
                ]

    half_day_data = find_half_day_leaves()

    unpaid_half = half_day_data["half_unpaid_leaves"]
    paid_half = half_day_data["half_paid_leaves"]

    paid_leave_dates = list(set(paid_leave_dates) - set(company_leave_dates))
    unpaid_leave_dates = list(set(unpaid_leave_dates) - set(company_leave_dates))
    paid_leave = len(paid_leave_dates) - paid_half
    unpaid_leave = len(unpaid_leave_dates) - unpaid_half

    return {
        "paid_leave": paid_leave,
        "unpaid_leaves": unpaid_leave,
        "total_leaves": paid_leave + unpaid_leave,
        # List of paid leave date between range
        "paid_leave_dates": paid_leave_dates,
        # List of un paid date between range
        "unpaid_leave_dates": unpaid_leave_dates,
        "leave_dates": unpaid_leave_dates + paid_leave_dates,
    }


if apps.is_installed("attendance"):

    def get_attendance(employee, start_date, end_date):
        """
        This method is used to render attendance details between the range

        Args:
            employee (obj): Employee user instance
            start_date (obj): start date of the period
            end_date (obj): end date of the period
        """
        Attendance = get_horilla_model_class(app_label="attendance", model="attendance")
        attendances_on_period = Attendance.objects.filter(
            employee_id=employee,
            attendance_date__range=(start_date, end_date),
            attendance_validated=True,
        )
        present_on = [
            attendance.attendance_date for attendance in attendances_on_period
        ]
        working_days_between_range = get_working_days(start_date, end_date)[
            "working_days_on"
        ]
        leave_dates = get_leaves(employee, start_date, end_date)["leave_dates"]
        conflict_dates = list(
            set(working_days_between_range)
            - set(attendances_on_period)
            - set(leave_dates)
        )
        conflict_dates = conflict_dates + [
            date
            for date in present_on
            if date in get_holiday_dates(start_date, end_date)
            or date
            in list(
                set(
                    get_company_leave_dates(start_date.year)
                    + get_company_leave_dates(end_date.year)
                )
            )
        ]

        return {
            "attendances_on_period": attendances_on_period,
            "present_on": present_on,
            "conflict_dates": conflict_dates,
        }


def hourly_computation(employee, wage, start_date, end_date):
    """
    Hourly salary computation for period.

    Args:
        employee (obj): Employee instance
        wage (float): wage of the employee
        start_date (obj): start of the pay period
        end_date (obj): end date of the period
    """
    if not apps.is_installed("attendance"):
        return {
            "basic_pay": 0,
            "loss_of_pay": 0,
        }
    attendance_data = get_attendance(employee, start_date, end_date)
    attendances_on_period = attendance_data["attendances_on_period"]
    
    # Get total working days in the period based on employee's shift schedule
    # This properly respects the employee's assigned work days (e.g., Mon-Fri)
    working_days_data = get_employee_working_days(employee, start_date, end_date)
    total_working_days = working_days_data["total_working_days"]
    working_days_dates = working_days_data["working_days_on"]
    company_leave_dates = working_days_data["company_leave_dates"]  # Holidays
    
    # Get leave dates to exclude from absence calculation
    leave_data = get_leaves(employee, start_date, end_date)
    leave_dates = leave_data.get("leave_dates", [])
    
    # Filter out attendance records that fall on holidays
    # Attendance on holidays should not be counted for regular pay calculation
    regular_attendances = [
        att for att in attendances_on_period 
        if att.attendance_date not in company_leave_dates
    ]
    
    # Get attendance dates (only regular working days, not holidays)
    attendance_dates = [attendance.attendance_date for attendance in regular_attendances]
    
    # Calculate absent days (working days without attendance and not on leave)
    # Note: Holidays are already excluded from working_days_dates by get_working_days()
    absent_dates = [
        day for day in working_days_dates 
        if day not in attendance_dates and day not in leave_dates
    ]
    absent_days = len(absent_dates)

    # Calculate actual worked hours and undertime (only for regular working days)
    total_worked_seconds = 0
    total_undertime_seconds = 0
    total_required_seconds = 0  # Track total required hours for calculating daily rate
    attendance_count_for_avg = 0  # Count only attendances with valid min_hours

    for attendance in regular_attendances:
        # Calculate worked hours (excluding overtime)
        worked_seconds = attendance.at_work_second - attendance.overtime_second
        total_worked_seconds += worked_seconds
        worked_hours = worked_seconds / 3600

        # Get minimum required hours
        min_hour_str = attendance.minimum_hour
        if min_hour_str and ':' in str(min_hour_str):
            hours, minutes = map(int, str(min_hour_str).split(':'))
            min_hours = hours + minutes / 60
            min_seconds = (hours * 3600) + (minutes * 60)
        else:
            min_hours = 8  # Default to 8 hours if not specified
            min_seconds = 8 * 3600
        
        # Only count attendance with actual required hours for average calculation
        if min_hours > 0:
            total_required_seconds += min_seconds
            attendance_count_for_avg += 1

        # Calculate undertime (only if there's a minimum requirement)
        if min_hours > 0 and worked_hours < min_hours:
            undertime_seconds = (min_hours - worked_hours) * 3600
            total_undertime_seconds += undertime_seconds

    # Calculate average daily required hours (for converting undertime to days)
    if attendance_count_for_avg > 0:
        avg_daily_seconds = total_required_seconds / attendance_count_for_avg
    else:
        avg_daily_seconds = 8 * 3600  # Default 8 hours

    # Check for leave credit deductions that cover undertime
    # If leave credits were used, add covered time to worked hours (treated as paid)
    # and reduce the undertime accordingly
    covered_seconds = 0
    if apps.is_installed("leave"):
        try:
            UndertimeLeaveDeduction = get_horilla_model_class(
                app_label="leave", model="undertimeleavededuction"
            )
            
            # Get all leave deductions for this employee in this period
            leave_deductions = UndertimeLeaveDeduction.objects.filter(
                employee_id=employee,
                deduction_date__range=(start_date, end_date)
            )
            
            # Sum up covered minutes (converted to seconds)
            covered_seconds = sum(
                (getattr(d, 'undertime_covered_minutes', 0) or 0) * 60 
                for d in leave_deductions
            )
            
            # Add covered time to worked hours (treated as paid leave time)
            total_worked_seconds += covered_seconds
            
            # Reduce undertime by covered amount
            total_undertime_seconds = max(0, total_undertime_seconds - covered_seconds)
        except Exception:
            # If leave module has issues, continue without adjustment
            pass

    # Calculate wage rates
    wage_in_second = wage / 3600
    
    # Calculate absent day deduction (full day wage for each absent day)
    # Daily wage = hourly wage * average daily required hours
    daily_wage = wage_in_second * avg_daily_seconds
    absent_deduction = absent_days * daily_wage
    
    # Calculate undertime deduction (now reduced by leave credit coverage)
    undertime_deduction = float(f"{(wage_in_second * total_undertime_seconds):.2f}")
    
    # Total loss of pay = absent days deduction + undertime deduction
    total_loss_of_pay = absent_deduction + undertime_deduction
    
    # Calculate LOP days (absent days + undertime converted to days)
    undertime_in_days = total_undertime_seconds / avg_daily_seconds if avg_daily_seconds > 0 else 0
    lop_days = absent_days + undertime_in_days
    
    # Calculate basic pay: expected pay for all working days minus loss of pay
    # Expected pay = total working days * daily wage
    expected_pay = total_working_days * daily_wage
    basic_pay = float(f"{(expected_pay - total_loss_of_pay):.2f}")
    
    # Paid days = working days - absent days - undertime equivalent days
    paid_days = total_working_days - lop_days
    
    # Calculate weekend days in the period (based on employee's non-scheduled days)
    date_range = get_date_range(start_date, end_date)
    weekend_dates = [d for d in date_range if d not in working_days_dates and d not in company_leave_dates]
    
    # Get minimum working hours from first attendance or default to 8
    min_work_hours = 8.0
    if regular_attendances:
        first_att = regular_attendances[0]
        min_hour_str = first_att.minimum_hour
        if min_hour_str and ':' in str(min_hour_str):
            hours, minutes = map(int, str(min_hour_str).split(':'))
            min_work_hours = hours + minutes / 60

    # Calculate undertime in hours for display
    undertime_hours = total_undertime_seconds / 3600
    undertime_in_days = total_undertime_seconds / avg_daily_seconds if avg_daily_seconds > 0 else 0

    return {
        "basic_pay": basic_pay,
        "loss_of_pay": float(f"{total_loss_of_pay:.2f}"),
        "paid_days": round(paid_days, 2),
        "unpaid_days": round(lop_days, 2),
        # Additional breakdown info
        "total_working_days": total_working_days,
        "hourly_rate": wage,
        "min_work_hours": min_work_hours,
        "daily_rate": round(wage * min_work_hours, 2),
        "expected_full_pay": round(wage * min_work_hours * total_working_days, 2),
        "holidays": sorted(company_leave_dates),
        "weekends": sorted(weekend_dates),
        "absent_days": absent_days,
        # LOP breakdown details
        "absent_deduction": round(absent_deduction, 2),
        "undertime_hours": round(undertime_hours, 2),
        "undertime_days": round(undertime_in_days, 2),
        "undertime_deduction": round(undertime_deduction, 2),
    }


def find_half_day_leaves():
    """
    This method is used to return the half day leave details

    Args:
        employee (obj): Employee model instance
        start_date (obj): start date of the period
        end_date (obj): end date of the period
    """
    paid_queryset = []
    unpaid_queryset = []

    paid_leaves = list(filter(None, list(set(paid_queryset))))
    unpaid_leaves = list(filter(None, list(set(unpaid_queryset))))

    paid_half = len(paid_leaves) * 0.5
    unpaid_half = len(unpaid_leaves) * 0.5
    queryset = paid_leaves + unpaid_leaves
    total_leaves = len(queryset) * 0.50
    return {
        "half_day_query_set": queryset,
        "half_day_leaves": total_leaves,
        "half_paid_leaves": paid_half,
        "half_unpaid_leaves": unpaid_half,
    }


def daily_computation(employee, wage, start_date, end_date):
    """
    Hourly salary computation for period.

    Args:
        employee (obj): Employee instance
        wage (float): wage of the employee
        start_date (obj): start of the pay period
        end_date (obj): end date of the period
    """
    working_day_data = get_working_days(start_date, end_date)
    total_working_days = working_day_data["total_working_days"]

    leave_data = get_leaves(employee, start_date, end_date)

    contract = employee.contract_set.filter(contract_status="active").first()
    basic_pay = wage * total_working_days
    loss_of_pay = 0

    date_range = get_date_range(start_date, end_date)
    half_day_leaves_between_period_on_start_date = (
        employee.leaverequest_set.filter(
            leave_type_id__payment="unpaid",
            start_date__in=date_range,
            status="approved",
        )
        .exclude(start_date_breakdown="full_day")
        .count()
    )

    half_day_leaves_between_period_on_end_date = (
        employee.leaverequest_set.filter(
            leave_type_id__payment="unpaid", end_date__in=date_range, status="approved"
        )
        .exclude(end_date_breakdown="full_day")
        .exclude(start_date=F("end_date"))
        .count()
    )
    unpaid_half_leaves = (
        half_day_leaves_between_period_on_start_date
        + half_day_leaves_between_period_on_end_date
    ) * 0.5

    contract = employee.contract_set.filter(
        is_active=True, contract_status="active"
    ).first()

    unpaid_leaves = leave_data["unpaid_leaves"] - unpaid_half_leaves
    if contract.calculate_daily_leave_amount:
        loss_of_pay = (unpaid_leaves) * wage
    else:
        fixed_penalty = contract.deduction_for_one_leave_amount
        loss_of_pay = (unpaid_leaves) * fixed_penalty
    if contract.deduct_leave_from_basic_pay:
        basic_pay = basic_pay - loss_of_pay

    return {
        "basic_pay": basic_pay,
        "loss_of_pay": loss_of_pay,
        "paid_days": total_working_days,
        "unpaid_days": unpaid_leaves,
    }


def get_daily_salary(wage, wage_date) -> dict:
    """
    This method is used to calculate daily salary for the date
    """
    last_day = calendar.monthrange(wage_date.year, wage_date.month)[1]
    end_date = date(wage_date.year, wage_date.month, last_day)
    start_date = date(wage_date.year, wage_date.month, 1)
    working_days = get_working_days(start_date, end_date)["total_working_days"]
    day_wage = (
        wage / working_days if working_days else 0.0
    )  # if working_days != 0 else 0 #769

    return {
        "day_wage": day_wage,
    }


def months_between_range(wage, start_date, end_date):
    """
    This method is used to find the months between range
    """
    months_data = []

    for current_date in (
        start_date + relativedelta(months=i)
        for i in range(
            (end_date.year - start_date.year) * 12
            + end_date.month
            - start_date.month
            + 1
        )
    ):
        month = current_date.month
        year = current_date.year

        days_in_month = (
            current_date + relativedelta(day=1, months=1) - relativedelta(days=1)
        ).day

        # Calculate the end date for the current month
        current_end_date = current_date + relativedelta(day=days_in_month)
        current_end_date = min(current_end_date, end_date)
        working_days_on_month = get_working_days(
            current_date.replace(day=1), current_date.replace(day=days_in_month)
        )["total_working_days"]

        month_start_date = (
            date(year=year, month=month, day=1)
            if start_date < date(year=year, month=month, day=1)
            else start_date
        )
        total_working_days_on_period = get_working_days(
            month_start_date, current_end_date
        )["total_working_days"]

        month_info = {
            "month": month,
            "year": year,
            "days": days_in_month,
            "start_date": month_start_date.strftime("%Y-%m-%d"),
            "end_date": current_end_date.strftime("%Y-%m-%d"),
            # month period
            "working_days_on_period": total_working_days_on_period,
            "working_days_on_month": working_days_on_month,
            "per_day_amount": (
                wage / working_days_on_month if working_days_on_month else 0.0
            ),
            # if working_days_on_month != 0 else 0 #769,
        }

        months_data.append(month_info)
        # Set the start date for the next month as the first day of the next month
        current_date = (current_date + relativedelta(day=1, months=1)).replace(day=1)

    return months_data


def compute_yearly_taxable_amount(
    monthly_taxable_amount=None,
    default_yearly_taxable_amount=None,
    *args,
    **kwargs,
):
    """
    Compute yearly taxable amount custom logic
    eg:
        default_yearly_taxable_amount = monthly_taxable_amount * 12
    """
    return default_yearly_taxable_amount


def compute_net_pay(
    net_pay=None,
    gross_pay=None,
    total_pretax_deduction=None,
    total_post_tax_deduction=None,
    total_tax_deductions=None,
    loss_of_pay_amount=None,
    *args,
    **kwargs,
):
    """
    Compute net pay | Additional logic
    """

    return net_pay


def monthly_computation(employee, wage, start_date, end_date, *args, **kwargs):
    """
    Hourly salary computation for period.

    Args:
        employee (obj): Employee instance
        wage (float): wage of the employee
        start_date (obj): start of the pay period
        end_date (obj): end date of the period
    """
    basic_pay = 0
    month_data = months_between_range(wage, start_date, end_date)

    leave_data = get_leaves(employee, start_date, end_date)

    for data in month_data:
        basic_pay = basic_pay + (
            data["working_days_on_period"] * data["per_day_amount"]
        )

    contract = employee.contract_set.filter(contract_status="active").first()
    loss_of_pay = 0
    date_range = get_date_range(start_date, end_date)
    if apps.is_installed("leave"):
        start_date_leaves = (
            employee.leaverequest_set.filter(
                leave_type_id__payment="unpaid",
                start_date__in=date_range,
                status="approved",
            )
            .exclude(start_date_breakdown="full_day")
            .count()
        )
        end_date_leaves = (
            employee.leaverequest_set.filter(
                leave_type_id__payment="unpaid",
                end_date__in=date_range,
                status="approved",
            )
            .exclude(end_date_breakdown="full_day")
            .exclude(start_date=F("end_date"))
            .count()
        )
    else:
        start_date_leaves = 0
        end_date_leaves = 0

    half_day_leaves_between_period_on_start_date = start_date_leaves

    half_day_leaves_between_period_on_end_date = end_date_leaves

    unpaid_half_leaves = (
        half_day_leaves_between_period_on_start_date
        + half_day_leaves_between_period_on_end_date
    ) * 0.5

    contract = employee.contract_set.filter(
        is_active=True, contract_status="active"
    ).first()
    unpaid_leaves = abs(leave_data["unpaid_leaves"] - unpaid_half_leaves)
    paid_days = month_data[0]["working_days_on_period"] - unpaid_leaves
    daily_computed_salary = get_daily_salary(wage=wage, wage_date=start_date)[
        "day_wage"
    ]
    if contract.calculate_daily_leave_amount:
        loss_of_pay = (unpaid_leaves) * daily_computed_salary
    else:
        fixed_penalty = contract.deduction_for_one_leave_amount
        loss_of_pay = (unpaid_leaves) * fixed_penalty

    if contract.deduct_leave_from_basic_pay:
        basic_pay = basic_pay - loss_of_pay
    return {
        "basic_pay": basic_pay,
        "loss_of_pay": loss_of_pay,
        "month_data": month_data,
        "unpaid_days": unpaid_leaves,
        "paid_days": paid_days,
        "contract": contract,
    }


def compute_salary_on_period(employee, start_date, end_date, wage=None):
    """
    This method is used to compute salary on the start to end date period

    Args:
        employee (obj): Employee instance
        start_date (obj): start date of the period
        end_date (obj): end date of the period
    """
    contract = Contract.objects.filter(
        employee_id=employee, contract_status="active"
    ).first()
    if contract is None:
        return contract

    wage = contract.wage if wage is None else wage
    wage_type = contract.wage_type
    data = None
    if wage_type == "hourly":
        data = hourly_computation(employee, wage, start_date, end_date)
        month_data = months_between_range(wage, start_date, end_date)
        data["month_data"] = month_data
    elif wage_type == "daily":
        data = daily_computation(employee, wage, start_date, end_date)
        month_data = months_between_range(wage, start_date, end_date)
        data["month_data"] = month_data

    else:
        data = monthly_computation(employee, wage, start_date, end_date)
    data["contract_wage"] = wage
    data["contract"] = contract
    return data


def paginator_qry(qryset, page_number):
    """
    This method is used to paginate queryset
    """
    paginator = Paginator(qryset, get_pagination())
    qryset = paginator.get_page(page_number)
    return qryset


def calculate_employer_contribution(data):
    """
    This method is used to calculate the employer contribution
    """
    pay_head_data = data["pay_data"]
    deductions_to_process = [
        pay_head_data.get("pretax_deductions"),
        pay_head_data.get("post_tax_deductions"),
        pay_head_data.get("tax_deductions"),
        pay_head_data.get("net_deductions"),
    ]

    for deductions in deductions_to_process:
        if deductions:
            for deduction in deductions:
                if (
                    deduction.get("deduction_id")
                    and deduction.get("employer_contribution_rate", 0) > 0
                ):
                    object = Deduction.objects.filter(
                        id=deduction.get("deduction_id")
                    ).first()
                    if object:
                        amount = pay_head_data.get(object.based_on)
                        employer_contribution_amount = (
                            amount * object.employer_rate
                        ) / 100
                        deduction["based_on"] = object.based_on
                        deduction["employer_contribution_amount"] = (
                            employer_contribution_amount
                        )
    return data


def save_payslip(**kwargs):
    """
    This method is used to save the generated payslip
    """
    filtered_instance = Payslip.objects.filter(
        employee_id=kwargs["employee"],
        start_date=kwargs["start_date"],
        end_date=kwargs["end_date"],
    ).first()
    instance = filtered_instance if filtered_instance is not None else Payslip()
    instance.employee_id = kwargs["employee"]
    instance.group_name = kwargs.get("group_name")
    instance.start_date = kwargs["start_date"]
    instance.end_date = kwargs["end_date"]
    instance.status = kwargs["status"]
    instance.basic_pay = round(kwargs["basic_pay"], 2)
    instance.contract_wage = round(kwargs["contract_wage"], 2)
    instance.gross_pay = round(kwargs["gross_pay"], 2)
    instance.deduction = round(kwargs["deduction"], 2)
    instance.net_pay = round(kwargs["net_pay"], 2)
    instance.pay_head_data = kwargs["pay_data"]
    instance.save()
    instance.installment_ids.set(kwargs["installments"])
    return instance
