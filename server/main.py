"""
Muntomani - Server

Acest server NU salvează nimic pe disc și NU folosește bază de date.
Tot ce ține de un grup (membri, locații, mesaje) stă într-un dicționar Python
în memoria RAM (variabila `groups` mai jos). Imediat ce grupul e șters de
organizator (sau serverul repornește), datele dispar definitiv. Exact ca
cerința: "live cât timp există grupul".

Nu există login: oricine are codul grupului se poate alătura, trimițând
doar un nume. Identitatea fiecărui membru e un id generat aleator (uuid),
pe care aplicația client îl ține minte cât timp e deschisă.

Rulare locală (pentru testare pe calculator):
    pip install -r requirements.txt
    uvicorn main:app --reload --host 0.0.0.0 --port 8000

Pentru ca telefoanele să poată ajunge la acest server, trebuie pus online
(vezi README.md din rădăcina proiectului - recomandăm Render.com, plan gratuit).
"""

import random
import string
import time
import uuid
from typing import Dict, List

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Muntomani API")

# CORS deschis: aplicația mobilă apelează acest server direct, fără cookie-uri/sesiuni
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------
# "Baza de date": un singur dicționar, doar în RAM. Structura unui grup:
#
# groups["AB12CD"] = {
#     "nume": "Drumeție Bucegi",
#     "token_organizator": "...",   # secret, doar organizatorul îl are
#     "membri": {
#         "id-uuid-1": {"nume": "Andrei", "culoare": "#E53935",
#                       "lat": 45.4, "lon": 25.5, "ultima_actualizare": 169...,
#                       "organizator": True},
#         ...
#     },
#     "mesaje": [{"nume": "Andrei", "culoare": "#E53935", "text": "Salut!", "timp": 169...}],
# }
# ----------------------------------------------------------------------
groups: Dict[str, dict] = {}

CULORI = [
    "#E53935", "#1E88E5", "#43A047", "#FB8C00",
    "#8E24AA", "#00ACC1", "#FDD835", "#6D4C41",
    "#D81B60", "#3949AB",
]


def cod_grup_nou() -> str:
    """Cod scurt din 6 caractere, ușor de dictat sau scris pe hârtie la pornirea turei."""
    while True:
        cod = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if cod not in groups:
            return cod


# ----------------------------- Modele cereri -----------------------------

class CreareGrup(BaseModel):
    nume_grup: str
    nume_organizator: str


class AlaturareGrup(BaseModel):
    nume: str


class ActualizareLocatie(BaseModel):
    id_membru: str
    lat: float
    lon: float


class MesajNou(BaseModel):
    id_membru: str
    text: str


class StergereGrup(BaseModel):
    token_organizator: str


class PunctTraseu(BaseModel):
    lat: float
    lon: float


class SetareTraseu(BaseModel):
    token_organizator: str
    puncte: List[PunctTraseu]  # în ordine: start, [intermediare...], final


# ------------------------------- Endpoint-uri -------------------------------

@app.post("/grupuri")
def creeaza_grup(date: CreareGrup):
    """Organizatorul creează grupul. Devine automat primul membru."""
    cod = cod_grup_nou()
    id_membru = str(uuid.uuid4())
    token_organizator = str(uuid.uuid4())
    culoare = CULORI[0]

    groups[cod] = {
        "nume": date.nume_grup,
        "token_organizator": token_organizator,
        "membri": {
            id_membru: {
                "nume": date.nume_organizator,
                "culoare": culoare,
                "lat": None,
                "lon": None,
                "ultima_actualizare": None,
                "organizator": True,
            }
        },
        "mesaje": [],
        "traseu": None,
        "alerta_urs": None,  # None sau timestamp când s-a raportat
    }

    return {
        "cod_grup": cod,
        "id_membru": id_membru,
        "token_organizator": token_organizator,
        "culoare": culoare,
    }


@app.post("/grupuri/{cod}/membri")
def alatura_grup(cod: str, date: AlaturareGrup):
    """Un participant se alătură unui grup existent, folosind doar codul + un nume."""
    grup = groups.get(cod)
    if not grup:
        raise HTTPException(404, "Grupul nu există (a fost șters sau codul e greșit)")

    id_membru = str(uuid.uuid4())
    culoare = CULORI[len(grup["membri"]) % len(CULORI)]

    grup["membri"][id_membru] = {
        "nume": date.nume,
        "culoare": culoare,
        "lat": None,
        "lon": None,
        "ultima_actualizare": None,
        "organizator": False,
    }

    return {"id_membru": id_membru, "culoare": culoare, "nume_grup": grup["nume"]}


@app.post("/grupuri/{cod}/locatie")
def actualizeaza_locatie(cod: str, date: ActualizareLocatie):
    """Aplicația trimite periodic (ex: la 5-10 secunde) locația curentă a telefonului."""
    grup = groups.get(cod)
    if not grup:
        raise HTTPException(404, "Grupul nu există")
    membru = grup["membri"].get(date.id_membru)
    if not membru:
        raise HTTPException(404, "Nu faci parte din acest grup")

    membru["lat"] = date.lat
    membru["lon"] = date.lon
    membru["ultima_actualizare"] = time.time()
    return {"ok": True}


@app.get("/grupuri/{cod}")
def stare_grup(cod: str):
    grup = groups.get(cod)
    if not grup:
        raise HTTPException(404, "Grupul nu există")
    return {
        "nume": grup["nume"],
        "membri": [{"id": id_m, **info} for id_m, info in grup["membri"].items()],
        "mesaje": grup["mesaje"][-200:],
        "traseu": grup.get("traseu"),
        "alerta_urs": grup.get("alerta_urs"),
    }


@app.post("/grupuri/{cod}/urs")
def raporteaza_urs(cod: str, date: MesajNou):
    """Un participant raportează prezența unui urs - toți participanții vor fi alertați."""
    grup = groups.get(cod)
    if not grup:
        raise HTTPException(404, "Grupul nu există")
    if date.id_membru not in grup["membri"]:
        raise HTTPException(404, "Nu faci parte din acest grup")
    grup["alerta_urs"] = {
        "raportat_de": grup["membri"][date.id_membru]["nume"],
        "timp": time.time(),
    }
    return {"ok": True}


@app.delete("/grupuri/{cod}/urs")
def sterge_alerta_urs(cod: str, date: MesajNou):
    """Anulează alerta de urs (după ce pericolul a trecut)."""
    grup = groups.get(cod)
    if not grup:
        raise HTTPException(404, "Grupul nu există")
    grup["alerta_urs"] = None
    return {"ok": True}


@app.post("/grupuri/{cod}/mesaje")
def trimite_mesaj(cod: str, date: MesajNou):
    grup = groups.get(cod)
    if not grup:
        raise HTTPException(404, "Grupul nu există")
    membru = grup["membri"].get(date.id_membru)
    if not membru:
        raise HTTPException(404, "Nu faci parte din acest grup")

    grup["mesaje"].append({
        "nume": membru["nume"],
        "culoare": membru["culoare"],
        "text": date.text,
        "timp": time.time(),
    })
    return {"ok": True}


@app.delete("/grupuri/{cod}/membri/{id_membru}")
def paraseste_grup(cod: str, id_membru: str):
    """Un participant (nu organizatorul) părăsește grupul - dispare de pe harta celorlalți."""
    grup = groups.get(cod)
    if not grup:
        raise HTTPException(404, "Grupul nu există")
    if id_membru in grup["membri"]:
        del grup["membri"][id_membru]
    return {"ok": True}


@app.delete("/grupuri/{cod}")
def sterge_grup(cod: str, date: StergereGrup):
    """Doar organizatorul (cel care are token_organizator) poate șterge grupul definitiv."""
    grup = groups.get(cod)
    if not grup:
        raise HTTPException(404, "Grupul nu există")
    if grup["token_organizator"] != date.token_organizator:
        raise HTTPException(403, "Doar organizatorul poate șterge grupul")
    del groups[cod]
    return {"ok": True}


@app.get("/")
def sanatate():
    """Endpoint simplu ca să verifici rapid, din browser, că serverul e pornit."""
    return {"stare": "ok", "grupuri_active": len(groups)}


@app.post("/grupuri/{cod}/traseu")
def seteaza_traseu(cod: str, date: SetareTraseu):
    """
    Organizatorul trimite punctele alese (start, eventuale puncte
    intermediare, final). Serverul cere unui motor de rutare gratuit
    (OSRM, profil "foot") traseul real, urmărind poteci/drumuri - nu doar
    o linie dreaptă între puncte - și îl salvează pentru grup.
    """
    grup = groups.get(cod)
    if not grup:
        raise HTTPException(404, "Grupul nu există")
    if grup["token_organizator"] != date.token_organizator:
        raise HTTPException(403, "Doar organizatorul poate seta traseul")
    if len(date.puncte) < 2:
        raise HTTPException(400, "Traseul are nevoie de cel puțin un punct de start și unul final")

    coordonate = ";".join(f"{p.lon},{p.lat}" for p in date.puncte)
    try:
        r = requests.get(
            f"https://router.project-osrm.org/route/v1/foot/{coordonate}",
            params={"overview": "full", "geometries": "geojson"},
            timeout=10,
        )
        r.raise_for_status()
        raspuns = r.json()
    except requests.exceptions.RequestException:
        raise HTTPException(503, "Serviciul de trasee nu răspunde momentan. Încearcă din nou în puțin timp.")

    if raspuns.get("code") != "Ok":
        raise HTTPException(400, "Nu s-a putut genera un traseu între punctele alese.")

    coordonate_traseu = raspuns["routes"][0]["geometry"]["coordinates"]  # listă de [lon, lat]
    linie = [{"lat": lat, "lon": lon} for lon, lat in coordonate_traseu]

    grup["traseu"] = {"linie": linie}
    return grup["traseu"]


@app.delete("/grupuri/{cod}/traseu")
def sterge_traseu(cod: str, date: StergereGrup):
    grup = groups.get(cod)
    if not grup:
        raise HTTPException(404, "Grupul nu există")
    if grup["token_organizator"] != date.token_organizator:
        raise HTTPException(403, "Doar organizatorul poate șterge traseul")
    grup["traseu"] = None
    return {"ok": True}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
