import os
from io import BytesIO
from PIL import Image


def optimize_image(file):
    img = Image.open(file)
    img.thumbnail((300, 300))
    output = BytesIO()
    img.save(output, format=img.format)
    return output.getvalue()


def load_admin_ids():
    admin_ids = []
    file_path = os.path.join(os.path.dirname(__file__), 'admin_ids.txt')

    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            admin_ids = [line.strip() for line in f.readlines() if line.strip()]

    return admin_ids


def calculate_max_borrow_days(rating):
    if rating < 20:
        return 28
    elif rating < 50:
        return 35
    elif rating < 80:
        return 42
    elif rating < 100:
        return 49
    elif rating < 150:
        return 56
    elif rating < 200:
        return 63
    elif rating < 250:
        return 70
    elif rating < 300:
        return 77
    elif rating < 350:
        return 84
    elif rating < 400:
        return 91
    elif rating < 450:
        return 98
    else:
        return 105