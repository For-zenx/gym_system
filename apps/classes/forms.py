from django import forms

from .models import ClassSession

FIELD_CSS = "form-control"


class ClassSessionForm(forms.ModelForm):
    class Meta:
        model = ClassSession
        fields = [
            "title",
            "session_date",
            "start_time",
            "end_time",
            "instructor",
            "instructor_name",
            "price_usd",
            "capacity",
            "status",
            "notes",
        ]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": FIELD_CSS,
                    "placeholder": "Spin, Yoga…",
                    "maxlength": "100",
                    "required": True,
                    "autocomplete": "off",
                }
            ),
            "session_date": forms.DateInput(
                format="%Y-%m-%d",
                attrs={"type": "date", "class": FIELD_CSS, "required": True},
            ),
            "start_time": forms.TimeInput(
                format="%H:%M",
                attrs={"type": "time", "class": FIELD_CSS, "required": True},
            ),
            "end_time": forms.TimeInput(
                format="%H:%M",
                attrs={"type": "time", "class": FIELD_CSS},
            ),
            "instructor": forms.Select(
                attrs={"class": FIELD_CSS, "aria-label": "Entrenador del sistema"}
            ),
            "instructor_name": forms.TextInput(
                attrs={
                    "class": FIELD_CSS,
                    "placeholder": "Nombre",
                    "maxlength": "255",
                    "autocomplete": "off",
                    "aria-label": "Nombre del entrenador",
                }
            ),
            "price_usd": forms.NumberInput(
                attrs={
                    "class": FIELD_CSS,
                    "min": "0",
                    "step": "0.01",
                    "required": True,
                }
            ),
            "capacity": forms.NumberInput(
                attrs={
                    "class": FIELD_CSS,
                    "min": "1",
                    "placeholder": "Ilimitado",
                }
            ),
            "status": forms.Select(attrs={"class": FIELD_CSS}),
            "notes": forms.Textarea(
                attrs={
                    "class": FIELD_CSS,
                    "rows": 3,
                    "placeholder": "Detalle interno",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["session_date"].input_formats = ["%Y-%m-%d"]
        self.fields["start_time"].input_formats = ["%H:%M", "%H:%M:%S"]
        self.fields["end_time"].input_formats = ["%H:%M", "%H:%M:%S"]
        self.fields["end_time"].required = False
        self.fields["capacity"].required = False
        self.fields["instructor"].required = False
        self.fields["instructor_name"].required = False
        self.fields["notes"].required = False
        self.fields["instructor"].empty_label = "— Sin seleccionar —"

        if not self.instance.pk:
            self.fields.pop("status")
        else:
            self.fields["status"].required = True

        if not self.instance.pk and not self.is_bound:
            self.fields["price_usd"].initial = "0.00"

    def clean(self):
        cleaned = super().clean()
        instructor = cleaned.get("instructor")
        instructor_name = (cleaned.get("instructor_name") or "").strip()
        if not instructor and not instructor_name:
            raise forms.ValidationError(
                "Indique el entrenador registrado o escriba su nombre."
            )
        cleaned["instructor_name"] = instructor_name
        return cleaned

    def clean_capacity(self):
        capacity = self.cleaned_data.get("capacity")
        if capacity in ("", None):
            return None
        return capacity
