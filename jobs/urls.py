from .views import JobViewSet
from rest_framework.routers import DefaultRouter
from django.urls import path, include


router = DefaultRouter()
router.register(r"jobs", JobViewSet, basename="jobs")

urlpatterns = [
    path("", include(router.urls)),
]
