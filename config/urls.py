"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.views.static import serve
from apps.core import views as core_views
from apps.access import views as access_views
from apps.users.views import StaffProfileView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', core_views.dashboard, name='dashboard'),
    path('enrolamiento/', core_views.enrollment, name='enrollment'),
    path('enrolamiento/cedula/', core_views.enrollment_cedula_check, name='enrollment_cedula_check'),
    path('enrolamiento/facturacion/<str:codigo_afiliado>/', core_views.enrollment_billing, name='enrollment_billing'),
    path('tablet/acceso/', access_views.tablet_access_view, name='tablet_access'),
    path('tablet/enrolamiento/', access_views.tablet_enrollment_view, name='tablet_enrollment'),
    path('tablet/', RedirectView.as_view(url='/tablet/acceso/', permanent=True), name='tablet'),
    path('afiliados/', include('apps.clients.urls')),
    path('personal/enrolamiento/', core_views.staff_person_enrollment, name='staff_person_enrollment'),
    path('personal/', include('apps.clients.staff_urls')),
    path('billing/', include('apps.billing.urls')),
    path('casilleros/', include('apps.lockers.urls')),
    path('historial/', include('apps.access.urls')),
    path('estadisticas/', include('apps.stats.urls')),
    path('configuracion/', include('apps.users.urls')),
    path('perfil/', StaffProfileView.as_view(), name='staff_profile'),
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif getattr(settings, 'SERVE_FILES_LOCALLY', False):
    static_prefix = settings.STATIC_URL.lstrip('/')
    media_prefix = settings.MEDIA_URL.lstrip('/')
    urlpatterns += [
        re_path(
            rf"^{static_prefix}(?P<path>.*)$",
            serve,
            {"document_root": settings.STATIC_ROOT},
        ),
        re_path(
            rf"^{media_prefix}(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]
