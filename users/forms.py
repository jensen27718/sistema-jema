from django import forms
from allauth.account.forms import SignupForm

class CustomSignupForm(SignupForm):
    # Solo definimos nuestro campo extra.
    # Allauth ya se encarga de 'email', 'password1' y 'password2' automáticamente.
    fullname = forms.CharField(
        label="Nombre Completo", 
        widget=forms.TextInput(attrs={'placeholder': 'Tu nombre completo', 'class': 'form-control'})
    )

    def save(self, request):
        # Dejamos que Allauth guarde el usuario (y las contraseñas)
        user = super(CustomSignupForm, self).save(request)
        
        # Nosotros solo agregamos el nombre extra
        user.first_name = self.cleaned_data['fullname']
        user.save()
        return user