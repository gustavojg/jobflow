from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("jobs", views.JobViewSet, basename="job")

urlpatterns = [
    path("stats", views.stats, name="stats"),
    *router.urls,
]
