import os
import django

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'horilla.settings')
django.setup()

from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from leave.models import LeaveAccess

def grant_leave_access():
    try:
        # Get the permission
        content_type = ContentType.objects.get_for_model(LeaveAccess)
        permission = Permission.objects.get(
            content_type=content_type, 
            codename='view_leaveaccess'
        )
        
        # Get all users associated with employees
        users = User.objects.all()
        
        count = 0
        for user in users:
            if not user.has_perm('leave.view_leaveaccess'):
                user.user_permissions.add(permission)
                count += 1
        
        print(f"Successfully granted 'Leave Access' to {count} users.")
        print("Existing users with access already were skipped.")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    grant_leave_access()
