from django.shortcuts import render
from .models import Job


def index(request):
    jobs = Job.objects.all().order_by("-created_at")[:50]
    return render(request, "jobs/index.html", {"jobs": jobs})
