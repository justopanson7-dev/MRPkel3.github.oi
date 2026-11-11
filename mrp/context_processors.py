from .access import can_access, can_pay_sales, role_for_user
from .models import RoleProfile


def role_access(request):
    if not request.user.is_authenticated:
        return {}
    modules = ("dashboard", "inventory", "production", "purchasing", "sales", "finance", "users", "history")
    visibility = {
        module: can_access(request.user, module, "view")
        for module in modules
    }
    editability = {
        module: can_access(request.user, module, "change")
        for module in modules
    }
    role = role_for_user(request.user)
    role_label = dict(RoleProfile.Role.choices).get(role, "Manajer")
    return {
        "current_role": role,
        "current_role_label": role_label,
        "module_visibility": visibility,
        "module_editability": editability,
        "can_pay_sales": can_pay_sales(request.user),
    }
