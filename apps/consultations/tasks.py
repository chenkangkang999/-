from celery import shared_task


@shared_task
def execute_consultation(run_id):
    from apps.consultations.services.coordinator import execute_run

    execute_run(run_id)
