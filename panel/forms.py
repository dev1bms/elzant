from django import forms

_FIELD = "field"


class GuestInviteForm(forms.Form):
    """Add-a-guest form: just a name + phone. Normalization/dedupe happen in the
    view (needs WhatsAppConfig for the default country code)."""

    full_name = forms.CharField(
        label="اسم المدعو", max_length=120,
        widget=forms.TextInput(attrs={
            "class": _FIELD, "placeholder": "الاسم الكامل", "autocomplete": "name",
            "autofocus": "autofocus",
        }),
        error_messages={"required": "من فضلك اكتب اسم المدعو."},
    )
    phone = forms.CharField(
        label="رقم الهاتف", max_length=30,
        widget=forms.TextInput(attrs={
            "class": _FIELD, "placeholder": "مثال: 01001234567", "inputmode": "tel",
            "dir": "ltr",
        }),
        error_messages={"required": "من فضلك اكتب رقم الهاتف."},
    )
