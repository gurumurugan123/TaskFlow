from rest_framework import serializers
from .models import Job


class JobCreateSerializer(serializers.Serializer):
    task = serializers.CharField(max_length=100)
    data = serializers.JSONField(required=False, default=dict)

    def validate_task(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("task cannot be empty.")
        return value


class PreparePdfSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    content = serializers.CharField(allow_blank=True, required=False, default="")


class JobSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = ["id", "status", "payload", "attempts", "result", "created_at"]
        read_only_fields = ["id", "created_at"]
