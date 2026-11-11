from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/jobs/", consumers.JobFeedConsumer.as_asgi()),
    path("ws/jobs/<uuid:job_id>/", consumers.JobConsumer.as_asgi()),
]
