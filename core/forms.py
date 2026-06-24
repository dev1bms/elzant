from django import forms

from .models import Greeting

_FIELD_CLASS = (
    "w-full rounded-xl border border-cream-300 bg-white/85 px-4 py-3 text-burgundy-900 "
    "shadow-sm placeholder:text-burgundy-300 transition focus:border-gold-400 "
    "focus:outline-none focus:ring-2 focus:ring-gold-300/50"
)


class GreetingForm(forms.ModelForm):
    # Honeypot — real users never see or fill this; bots that do are rejected.
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Greeting
        fields = ["name", "message"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "maxlength": 60,
                    "placeholder": "اسمك",
                    "autocomplete": "name",
                    "class": _FIELD_CLASS,
                }
            ),
            "message": forms.Textarea(
                attrs={
                    "maxlength": 500,
                    "rows": 4,
                    "placeholder": "رسالتك للعروسين…",
                    "class": _FIELD_CLASS,
                }
            ),
        }
        error_messages = {
            "name": {"required": "من فضلك اكتب اسمك."},
            "message": {"required": "من فضلك اكتب رسالة التهنئة."},
        }

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("spam")
        return ""
