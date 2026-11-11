from rest_framework import serializers

from .handlers import HANDLERS
from .models import Job


class JobSerializer(serializers.ModelSerializer):
    kind = serializers.ChoiceField(choices=sorted(HANDLERS))
    duration_seconds = serializers.FloatField(read_only=True)

    class Meta:
        model = Job
        fields = [
            "id",
            "kind",
            "payload",
            "status",
            "progress",
            "result",
            "error",
            "created_at",
            "started_at",
            "finished_at",
            "duration_seconds",
        ]
        read_only_fields = [
            "id",
            "status",
            "progress",
            "result",
            "error",
            "created_at",
            "started_at",
            "finished_at",
        ]

    def validate_payload(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("payload must be a JSON object")
        return value
