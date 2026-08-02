"""
export_model.py

Завантажує попередньо натреновану модель MobileNetV2 з torchvision,
переводить її в режим інференсу (eval) і серіалізує через TorchScript
(torch.jit.trace) у файл model/model.pt.

TorchScript дозволяє завантажувати й виконувати модель без залежності
від Python-класу моделі — лише сам граф обчислень і ваги.
"""

import os
import torch
from torchvision.models import mobilenet_v2, MobileNet_V2_Weights


def export_model(output_path: str = "model/model.pt") -> None:
    # Створюємо директорію для моделі, якщо її ще немає
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Сучасний API: явно вказуємо ваги замість застарілого pretrained=True.
    # DEFAULT вказує на найкращий доступний набір ваг для цієї архітектури.
    weights = MobileNet_V2_Weights.DEFAULT
    model = mobilenet_v2(weights=weights)

    # ВАЖЛИВО: переводимо модель у режим інференсу.
    # Це вимикає Dropout і фіксує статистику BatchNorm — без цього
    # результати inference будуть нестабільними/неправильними.
    model.eval()

    # TorchScript trace вимагає "приклад" вхідних даних правильної форми:
    # [batch_size, channels, height, width] = [1, 3, 224, 224] для MobileNetV2.
    dummy_input = torch.randn(1, 3, 224, 224)

    # trace прогонює модель на dummy_input і записує послідовність операцій
    # у статичний граф — саме цей граф зберігається, а не Python-код моделі.
    with torch.no_grad():
        traced_model = torch.jit.trace(model, dummy_input)

    traced_model.save(output_path)
    print(f"Модель успішно експортовано в TorchScript: {output_path}")


if __name__ == "__main__":
    export_model()