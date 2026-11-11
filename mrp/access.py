from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import RoleProfile


ROLE_ACCESS = {
    RoleProfile.Role.ADMIN: {
        "view": {"dashboard", "inventory", "production", "purchasing", "sales", "finance", "users", "history"},
        "change": {"dashboard", "inventory", "production", "purchasing", "sales", "finance", "users", "history"},
    },
    RoleProfile.Role.MANAGER: {
        "view": {"dashboard", "inventory", "production", "purchasing", "sales", "finance", "history"},
        "change": set(),
    },
    RoleProfile.Role.WAREHOUSE: {
        "view": {"dashboard", "inventory", "purchasing"},
        "change": {"inventory", "purchasing"},
    },
    RoleProfile.Role.PRODUCTION: {
        "view": {"dashboard", "inventory", "production"},
        "change": {"production"},
    },
    RoleProfile.Role.SALES: {
        "view": {"dashboard", "inventory", "sales"},
        "change": {"sales"},
    },
    RoleProfile.Role.FINANCE: {
        "view": {"dashboard", "sales", "purchasing", "finance"},
        "change": {"finance"},
    },
}


def role_for_user(user):
    if user.is_superuser:
        return RoleProfile.Role.ADMIN
    try:
        return user.role_profile.role
    except RoleProfile.DoesNotExist:
        return RoleProfile.Role.MANAGER


def can_access(user, module, level="view"):
    if not user.is_authenticated:
        return False
    return module in ROLE_ACCESS.get(role_for_user(user), {}).get(level, set())


def can_pay_sales(user):
    return role_for_user(user) in {RoleProfile.Role.ADMIN, RoleProfile.Role.FINANCE}


def module_required(module, level="view"):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not can_access(request.user, module, level):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


def payment_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not can_pay_sales(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped
