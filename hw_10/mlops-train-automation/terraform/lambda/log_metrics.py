import json


def handler(event, context):
    """
    Умовне логування метрик після валідації.
    В реальному проєкті тут могло б бути логування в CloudWatch Metrics,
    запис у DynamoDB, або виклик MLflow Tracking API.
    """
    print("Logging metrics...")
    print(f"Received event: {json.dumps(event)}")

    # event тут — це те, що повернула попередня Lambda (validate.py),
    # оскільки в Step Function крок log_metrics йде одразу після validate.
    validation_status = event.get("status", "unknown")

    result = {
        "status": "logged",
        "message": "Metrics logged successfully",
        "validation_status": validation_status,
        "metrics": {
            "accuracy": 0.95,
            "loss": 0.12,
        },
    }

    print(f"Log result: {json.dumps(result)}")
    return result