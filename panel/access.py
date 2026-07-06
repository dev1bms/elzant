"""Access control for the family panel — enforced in the view layer, not templates.

Panel access requires an InviterProfile (or superuser). Data isolation: an
inviter sees only guests they invited, unless their profile grants can_view_all.
Every guest lookup must go through `visible_guests` / `guest_or_403` so a sender
can never reach another sender's guest by guessing an id in the URL.
"""

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from core.models import WeddingGuest


def inviter_profile(user):
    return getattr(user, "inviter_profile", None)


def is_inviter(user):
    return bool(user.is_authenticated and (user.is_superuser or inviter_profile(user)))


def can_view_all(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = inviter_profile(user)
    return bool(profile and profile.can_view_all)


def inviter_required(view):
    """Require login AND panel membership (InviterProfile or superuser)."""

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url="panel:login")
        if not is_inviter(request.user):
            raise PermissionDenied("ليست لديك صلاحية استخدام لوحة الدعوات.")
        return view(request, *args, **kwargs)

    return wrapped


def visible_guests(user, scope="mine"):
    """Queryset of guests this user may see. scope='all' only if allowed."""
    qs = WeddingGuest.objects.select_related("invited_by", "invited_by__inviter_profile")
    if scope == "all" and can_view_all(user):
        return qs
    return qs.filter(invited_by=user)


def guest_or_403(user, guest_id):
    """Fetch a guest the user is allowed to act on, else raise 403/404."""
    from django.shortcuts import get_object_or_404

    guest = get_object_or_404(WeddingGuest, pk=guest_id)
    if can_view_all(user) or guest.invited_by_id == user.id:
        return guest
    raise PermissionDenied("لا يمكنك الوصول إلى مدعوٍّ لم تدعُه.")
