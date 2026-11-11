import os

import structlog
from celery import Celery
from celery.signals import setup_logging, task_prerun

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("jobflow")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@setup_logging.connect
def _keep_structlog(**_kwargs) -> None:
    """Stop Celery from hijacking the root logger; Django settings already configured it."""


@task_prerun.connect
def _bind_task_context(task_id: str, task, **_kwargs) -> None:
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(task_id=task_id, task=task.name)
