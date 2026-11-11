from django.urls import include, path

from jobs import views

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("readyz", views.readyz, name="readyz"),
    path("metrics", views.metrics, name="metrics"),
    path("api/", include("jobs.urls")),
]
