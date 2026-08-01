import json

from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from redis_client import redis_client

from .models import Job
from .queue import enqueue_job
from .serializers import JobCreateSerializer, JobSerializer, PreparePdfSerializer


class JobViewSet(viewsets.ViewSet):
    """
    POST /jobs/        → create job
    GET  /jobs/{id}/   → get job status
    """

    def create(self, request):
        serializer = JobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        job_id = enqueue_job(serializer.validated_data)
        return Response(
            {"id": job_id, "status": Job.STATUS_PENDING},
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, pk=None):
        job_data = redis_client.hgetall(f"job:{pk}")

        if job_data:
            if job_data.get("payload"):
                job_data["payload"] = json.loads(job_data["payload"])
            if job_data.get("result"):
                job_data["result"] = json.loads(job_data["result"])
            else:
                job_data["result"] = None
            return Response(job_data, status=status.HTTP_200_OK)

        try:
            job = Job.objects.get(id=pk)
        except Job.DoesNotExist:
            return Response(
                {"error": "Job not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(JobSerializer(job).data, status=status.HTTP_200_OK)


class PreparePdfView(APIView):
    """
    POST /pdfs/prepare/

    Returns immediately with a job id. PDF is built in the background worker.
    """

    def post(self, request):
        serializer = PreparePdfSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payload = {
            "task": "prepare_pdf",
            "data": {
                "title": serializer.validated_data["title"],
                "content": serializer.validated_data.get("content", ""),
            },
        }
        job_id = enqueue_job(payload)

        return Response(
            {
                "message": "PDF preparation started",
                "job_id": job_id,
                "status": Job.STATUS_PENDING,
                "status_url": f"/jobs/{job_id}/",
            },
            status=status.HTTP_202_ACCEPTED,
        )
