import json


def handler(event, context):
    """
    Умовна валідація вхідних даних для тренувального pipeline.
    В реальному проєкті тут була б перевірка схеми датасету,
    відсутності пропусків, коректності типів тощо.
    """
    print("Validating data...")
    print(f"Received event: {json.dumps(event)}")

    # Умовний, спрощений результат валідації —
    # у реальному сценарії тут повертався б True/False
    # залежно від фактичної перевірки даних.
    result = {
        "status": "valid",
        "message": "Data validation completed successfully",
        "input": event,
    }

    print(f"Validation result: {json.dumps(result)}")
    return result