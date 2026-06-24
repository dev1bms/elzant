from django import forms

from .models import Greeting

_FIELD_CLASS = (
    "w-full rounded-lg border border-sand-300 bg-white px-5 py-4 text-charcoal "
    "placeholder:text-charcoal-soft/50 outline-none transition "
    "focus:border-burgundy-500 focus:ring-1 focus:ring-burgundy-500/30"
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
