from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DeadLetterJobsView, JobViewSet, PreparePdfView

router = DefaultRouter()
router.register(r"jobs", JobViewSet, basename="jobs")

urlpatterns = [
    path("pdfs/prepare/", PreparePdfView.as_view(), name="prepare-pdf"),
    path("jobs/dead/", DeadLetterJobsView.as_view(), name="jobs-dead"),
    path("", include(router.urls)),
]
