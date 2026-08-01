from rest_framework import viewsets, status
from .serializers import JobSerializer, JobCreateSerializer
import uuid
import json
from .models import Job
from redis_client import redis_client
from rest_framework.response import Response


class JobViewSet(viewsets.ViewSet):
    """
    POST /jobs/        → create job
    GET  /jobs/{id}/   → get job status
    """

    def create(self, request):
        serializer = JobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        payload = serializer.validated_data
        job_id = str(uuid.uuid4())

        # 1) Save in Postgres (history)
        Job.objects.create(
            id=job_id,
            status=Job.STATUS_PENDING,
            payload=payload,
            attempts=0,
        )

        # 2) Save live state in Redis
        redis_client.hset(
            f"job:{job_id}",
            mapping={
                "id": job_id,
                "status": Job.STATUS_PENDING,
                "payload": json.dumps(payload),
                "attempts": "0",
                "result": "",
            },
        )
        redis_client.lpush("queue:pending", job_id)

        return Response(
            {
                "id": job_id,
                "status": Job.STATUS_PENDING,
            },
            status=status.HTTP_201_CREATED,
        )

    def retrieve(self, request, pk=None):
        # Prefer Redis (live status)
        job_data = redis_client.hgetall(f"job:{pk}")

        if job_data:
            if job_data.get("payload"):
                job_data["payload"] = json.loads(job_data["payload"])
            if job_data.get("result"):
                job_data["result"] = json.loads(job_data["result"])
            else:
                job_data["result"] = None
            return Response(job_data, status=status.HTTP_200_OK)

        # Fallback to DB
        try:
            job = Job.objects.get(id=pk)
        except Job.DoesNotExist:
            return Response(
                {"error": "Job not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(JobSerializer(job).data, status=status.HTTP_200_OK)
