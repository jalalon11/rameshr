"""
Module: payroll.tax_calc

This module previously contained functions for calculating the taxable amount using
Federal Tax / Filing Status. This feature has been removed from the system.
"""

import logging

logger = logging.getLogger(__name__)


def calculate_taxable_amount(**kwargs):
    """Calculate the taxable amount for a given employee within a specific period.
    
    This function has been disabled as Federal Tax / Filing Status feature has been removed.
    
    Returns:
        float: Always returns 0 as federal tax calculation is disabled.
    """
    return 0
