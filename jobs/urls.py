from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import JobViewSet, PreparePdfView

router = DefaultRouter()
router.register(r"jobs", JobViewSet, basename="jobs")

urlpatterns = [
    path("pdfs/prepare/", PreparePdfView.as_view(), name="prepare-pdf"),
    path("", include(router.urls)),
]
