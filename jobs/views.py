import json

from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from redis_client import redis_client

from .idempotency import IdempotencyConflict
from .models import Job
from .queue import enqueue_job, list_dead_letter_jobs
from .serializers import JobCreateSerializer, JobSerializer, PreparePdfSerializer


def _get_idempotency_key(request) -> str | None:
    """Read Idempotency-Key from header (Stripe-style) or optional body field."""
    key = request.headers.get("Idempotency-Key")
    if key:
        return key.strip()
    body_key = request.data.get("idempotency_key")
    if body_key:
        return str(body_key).strip()
    return None


def _job_status(job_id: str) -> str:
    status_value = redis_client.hget(f"job:{job_id}", "status")
    if status_value:
        return status_value
    try:
        return Job.objects.get(id=job_id).status
    except Job.DoesNotExist:
        return Job.STATUS_PENDING


class JobViewSet(viewsets.ViewSet):
    """
    POST /jobs/        → create job
    GET  /jobs/{id}/   → get job status
    """

    def create(self, request):
        serializer = JobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            job_id, created = enqueue_job(
                serializer.validated_data,
                idempotency_key=_get_idempotency_key(request),
            )
        except IdempotencyConflict as exc:
            return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(
            {
                "id": job_id,
                "status": _job_status(job_id),
                "idempotent_replay": not created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
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
    Send header Idempotency-Key to avoid duplicate PDF jobs on retry/double-click.
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

        try:
            job_id, created = enqueue_job(
                payload,
                idempotency_key=_get_idempotency_key(request),
            )
        except IdempotencyConflict as exc:
            return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(
            {
                "message": "PDF preparation started" if created else "Existing job returned",
                "job_id": job_id,
                "status": _job_status(job_id),
                "status_url": f"/jobs/{job_id}/",
                "idempotent_replay": not created,
            },
            status=status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK,
        )


class DeadLetterJobsView(APIView):
    """GET /jobs/dead/ — list permanently failed jobs in the dead-letter queue."""

    def get(self, request):
        limit = int(request.query_params.get("limit", 50))
        job_ids = list_dead_letter_jobs(limit=limit)
        jobs = []
        for job_id in job_ids:
            job_data = redis_client.hgetall(f"job:{job_id}")
            if job_data:
                if job_data.get("payload"):
                    job_data["payload"] = json.loads(job_data["payload"])
                if job_data.get("result"):
                    job_data["result"] = json.loads(job_data["result"])
                jobs.append(job_data)
        return Response({"count": len(jobs), "jobs": jobs})
