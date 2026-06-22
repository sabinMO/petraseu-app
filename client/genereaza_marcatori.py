"""
Generează iconițele colorate folosite pe hartă pentru fiecare participant.

Rulează acest script O SINGURĂ DATĂ pe calculator (nu pe telefon!):
    python genereaza_marcatori.py

El creează fișierele PNG în assets/markers/, care vor fi incluse în aplicație.
Aplicația finală (cea de pe telefon) NU are nevoie de Pillow ca să ruleze -
folosește doar aceste imagini deja generate.
"""

from PIL import Image, ImageDraw

# Aceeași listă de culori ca pe server (server/main.py -> CULORI)
CULORI = [
    "#E53935", "#1E88E5", "#43A047", "#FB8C00",
    "#8E24AA", "#00ACC1", "#FDD835", "#6D4C41",
    "#D81B60", "#3949AB",
]

DIMENSIUNE = 64  # pixeli


def hex_to_rgb(culoare_hex):
    culoare_hex = culoare_hex.lstrip("#")
    return tuple(int(culoare_hex[i:i + 2], 16) for i in (0, 2, 4))


def genereaza_marcator(culoare_hex, cale_fisier):
    img = Image.new("RGBA", (DIMENSIUNE, DIMENSIUNE), (0, 0, 0, 0))
    desen = ImageDraw.Draw(img)

    centru = DIMENSIUNE // 2
    raza = DIMENSIUNE // 2 - 4

    # cerc colorat cu contur alb (vizibil pe orice fundal de hartă)
    desen.ellipse(
        [centru - raza, centru - raza, centru + raza, centru + raza],
        fill=hex_to_rgb(culoare_hex) + (255,),
        outline=(255, 255, 255, 255),
        width=4,
    )
    img.save(cale_fisier)


if __name__ == "__main__":
    import os

    folder = os.path.join(os.path.dirname(__file__), "assets", "markers")
    os.makedirs(folder, exist_ok=True)

    for culoare in CULORI:
        nume_fisier = f"marker_{culoare.lstrip('#')}.png"
        cale = os.path.join(folder, nume_fisier)
        genereaza_marcator(culoare, cale)
        print("Generat:", cale)

    print("\nGata! Iconițele sunt în client/assets/markers/")
