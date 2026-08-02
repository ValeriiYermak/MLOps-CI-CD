"""
inference.py

Завантажує TorchScript-модель (model/model.pt) і виконує inference
на зображенні, переданому як аргумент командного рядка.
Виводить top-3 передбачення (class_id + confidence).

Використання:
    python3 app/inference.py шлях/до/зображення.jpg
"""

import sys
import torch
from PIL import Image
from torchvision.models import MobileNet_V2_Weights


def run_inference(image_path: str, model_path: str = "model/model.pt") -> None:
    # Завантажуємо TorchScript-модель. torch.jit.load не потребує
    # оригінального Python-класу моделі — граф обчислень уже "заморожений".
    model = torch.jit.load(model_path)
    model.eval()

    # Використовуємо той самий набір трансформацій (resize, crop, normalize),
    # з яким модель тренувалась — це критично для коректного результату.
    weights = MobileNet_V2_Weights.DEFAULT
    preprocess = weights.transforms()

    # Відкриваємо зображення і примусово конвертуємо в RGB
    # (захист від PNG з альфа-каналом чи grayscale-зображень).
    img = Image.open(image_path).convert("RGB")

    # Препроцесинг перетворює PIL.Image у тензор форми [C, H, W].
    # unsqueeze(0) додає вимір батча -> [1, C, H, W], бо модель
    # завжди очікує батч, навіть якщо в ньому одне зображення.
    input_tensor = preprocess(img).unsqueeze(0)

    # no_grad() вимикає обчислення градієнтів - для inference вони
    # не потрібні, це економить пам'ять і час.
    with torch.no_grad():
        output = model(input_tensor)
        probabilities = torch.nn.functional.softmax(output[0], dim=0)

    top3 = torch.topk(probabilities, 3)

    print(f"Top-3 передбачення для '{image_path}':")
    for rank, (score, class_id) in enumerate(zip(top3.values, top3.indices), start=1):
        print(f"  {rank}. class_id={class_id.item()}, confidence={score.item():.4f}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Використання: python3 app/inference.py <шлях_до_зображення>")
        sys.exit(1)

    run_inference(sys.argv[1])