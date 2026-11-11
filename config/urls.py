from django.urls import include, path
from django.views.generic import TemplateView

from jobs import views

urlpatterns = [
    path("", TemplateView.as_view(template_name="index.html"), name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("readyz", views.readyz, name="readyz"),
    path("metrics", views.metrics, name="metrics"),
    path("api/", include("jobs.urls")),
]
