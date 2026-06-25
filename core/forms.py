from django import forms

from .imaging import ImageError, validate_upload
from .models import Greeting

_FIELD_CLASS = "field"  # styled by the design system (tailwind/input.css)


class GreetingForm(forms.ModelForm):
    # Honeypot — real users never see or fill this; bots that do are rejected.
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    # Optional photo. ImageField verifies it decodes as an image (Pillow);
    # validate_upload adds size/type checks with friendly Arabic messages. The
    # uploaded file is processed in the view (resize/EXIF-strip/thumbnail).
    photo = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(
            attrs={"accept": "image/jpeg,image/png,image/webp", "id": "id_photo", "class": "hidden"}
        ),
        error_messages={"invalid_image": "تعذّر قراءة الصورة — تأكّد أنها صورة صحيحة."},
    )

    class Meta:
        model = Greeting
        fields = ["name", "message", "card_template"]
        widgets = {
            "name": forms.TextInput(
                attrs={"maxlength": 60, "placeholder": "اسمك", "autocomplete": "name", "class": _FIELD_CLASS}
            ),
            "message": forms.Textarea(
                attrs={"maxlength": 500, "rows": 4, "placeholder": "رسالتك للعروسين…", "class": _FIELD_CLASS}
            ),
            # Set by the template-chips JS; never a free text input.
            "card_template": forms.HiddenInput(),
        }
        error_messages = {
            "name": {"required": "من فضلك اكتب اسمك."},
            "message": {"required": "من فضلك اكتب رسالة التهنئة."},
        }

    def clean_website(self):
        if self.cleaned_data.get("website"):
            raise forms.ValidationError("spam")
        return ""

    def clean_photo(self):
        f = self.cleaned_data.get("photo")
        if f:
            try:
                validate_upload(f)
            except ImageError as exc:
                raise forms.ValidationError(str(exc))
        return f
