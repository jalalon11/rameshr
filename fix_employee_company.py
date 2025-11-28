"""
Fix Employee Company Assignment

This script assigns the default company to all employees who don't have a company assigned.
This will make previously imported employees visible in the employee list.

Usage:
    python fix_employee_company.py
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'horilla.settings')
django.setup()

from employee.models import EmployeeWorkInformation
from base.models import Company

def fix_employee_company_assignments():
    """
    Assign default company to all employees without a company
    """
    print("=" * 80)
    print("FIX EMPLOYEE COMPANY ASSIGNMENTS")
    print("=" * 80)
    
    # Get the default company (first company in the system)
    company = Company.objects.first()
    
    if not company:
        print("\nERROR: No companies found in the system!")
        print("Please create a company first before running this script.")
        return
    
    print(f"\nDefault Company: {company.company} (ID: {company.id})")
    
    # Find all employee work information records without a company
    work_infos_without_company = EmployeeWorkInformation.objects.filter(
        company_id__isnull=True
    )
    
    count = work_infos_without_company.count()
    
    if count == 0:
        print("\nAll employees already have a company assigned!")
        print("No changes needed.")
        return
    
    print(f"\nFound {count} employees without a company assignment:")
    print("-" * 80)
    
    for work_info in work_infos_without_company:
        emp = work_info.employee_id
        print(f"  - {emp.badge_id}: {emp.employee_first_name} {emp.employee_last_name}")
    
    print("-" * 80)
    print(f"\nAssigning '{company.company}' to all {count} employees...")
    
    # Update all work information records to have the default company
    updated_count = work_infos_without_company.update(company_id=company)
    
    print(f"\n✓ SUCCESS: Updated {updated_count} employee records")
    print("\nThese employees should now be visible in the employee list!")
    print("=" * 80)

if __name__ == "__main__":
    fix_employee_company_assignments()
