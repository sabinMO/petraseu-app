"""
Comunicarea aplicației cu serverul Muntomani.

Toate apelurile sunt cereri HTTP simple (biblioteca `requests`), fără login,
fără cookie-uri. Identitatea unui membru e doar id_membru-ul primit la
creare/alăturare, păstrat în memoria aplicației cât timp e deschisă.
"""

import requests

# IMPORTANT: înlocuiește cu adresa serverului tău odată ce îl pui online
# (vezi README.md -> "Pune serverul online"). Pentru testare pe calculator,
# dacă rulezi serverul local, poți lăsa "http://127.0.0.1:8000".
SERVER_URL = "http://127.0.0.1:8000"

TIMEOUT = 8  # secunde, ca aplicația să nu rămână blocată dacă nu e semnal


class EroareRetea(Exception):
    """Eroare prietenoasă, afișată în interfață, în loc de un traceback tehnic."""
    pass


def _trateaza(functie_cerere):
    try:
        r = functie_cerere()
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        raise EroareRetea("Serverul nu răspunde. Verifică semnalul/conexiunea.")
    except requests.exceptions.ConnectionError:
        raise EroareRetea("Nu mă pot conecta la server. Verifică adresa SERVER_URL.")
    except requests.exceptions.HTTPError as e:
        try:
            detaliu = e.response.json().get("detail", str(e))
        except Exception:
            detaliu = str(e)
        raise EroareRetea(detaliu)


def creeaza_grup(nume_grup, nume_organizator):
    return _trateaza(lambda: requests.post(
        f"{SERVER_URL}/grupuri",
        json={"nume_grup": nume_grup, "nume_organizator": nume_organizator},
        timeout=TIMEOUT,
    ))


def alatura_grup(cod, nume):
    return _trateaza(lambda: requests.post(
        f"{SERVER_URL}/grupuri/{cod}/membri",
        json={"nume": nume},
        timeout=TIMEOUT,
    ))


def trimite_locatie(cod, id_membru, lat, lon):
    return _trateaza(lambda: requests.post(
        f"{SERVER_URL}/grupuri/{cod}/locatie",
        json={"id_membru": id_membru, "lat": lat, "lon": lon},
        timeout=TIMEOUT,
    ))


def stare_grup(cod):
    return _trateaza(lambda: requests.get(
        f"{SERVER_URL}/grupuri/{cod}", timeout=TIMEOUT
    ))


def trimite_mesaj(cod, id_membru, text):
    return _trateaza(lambda: requests.post(
        f"{SERVER_URL}/grupuri/{cod}/mesaje",
        json={"id_membru": id_membru, "text": text},
        timeout=TIMEOUT,
    ))


def raporteaza_urs(cod, id_membru):
    return _trateaza(lambda: requests.post(
        f"{SERVER_URL}/grupuri/{cod}/urs",
        json={"id_membru": id_membru, "text": "urs"},
        timeout=TIMEOUT
    ))


def sterge_alerta_urs(cod, id_membru):
    return _trateaza(lambda: requests.delete(
        f"{SERVER_URL}/grupuri/{cod}/urs",
        json={"id_membru": id_membru, "text": ""},
        timeout=TIMEOUT,
    ))


def paraseste_grup(cod, id_membru):
    return _trateaza(lambda: requests.delete(
        f"{SERVER_URL}/grupuri/{cod}/membri/{id_membru}", timeout=TIMEOUT
    ))


def _cauta_photon(text):
    r = requests.get(
        "https://photon.komoot.io/api/",
        params={"q": text, "limit": 6, "lat": 45.9432, "lon": 24.9668},
        headers={"User-Agent": "PeTraseu/1.0 Android",
                 "Accept": "application/json"},
        timeout=6,
    )
    r.raise_for_status()
    rezultate = []
    for el in r.json().get("features", []):
        prop = el.get("properties", {})
        coord = el.get("geometry", {}).get("coordinates")
        if not coord:
            continue
        lon, lat = coord
        parti = [prop.get("name") or text]
        for cheie in ("street", "city", "county", "country"):
            val = prop.get(cheie)
            if val and val not in parti:
                parti.append(val)
        rezultate.append({"nume": ", ".join(parti[:3]), "lat": lat, "lon": lon})
    return rezultate


def _cauta_nominatim(text):
    """Nominatim (OSM) - fallback dacă Photon e indisponibil."""
    r = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": text, "format": "json", "limit": 6,
                "accept-language": "ro", "countrycodes": "ro"},
        headers={"User-Agent": "PeTraseu/1.0 (drumetie montana Romania)"},
        timeout=6,
    )
    r.raise_for_status()
    return [
        {"nume": loc["display_name"][:80], "lat": float(loc["lat"]), "lon": float(loc["lon"])}
        for loc in r.json()
    ]


def cauta_locatie(text):
    """Caută locuri după nume. Încearcă Photon mai întâi, Nominatim ca fallback."""
    if len(text.strip()) < 3:
        return []
    try:
        rezultate = _cauta_photon(text)
        if rezultate:
            return rezultate
    except Exception:
        pass
    try:
        return _cauta_nominatim(text)
    except Exception as e:
        raise EroareRetea(f"Căutarea nu a funcționat: {e}")


def seteaza_traseu(cod, token_organizator, puncte):
    """puncte: listă de dict-uri {"lat": ..., "lon": ...}, în ordine: start, intermediare, final"""
    return _trateaza(lambda: requests.post(
        f"{SERVER_URL}/grupuri/{cod}/traseu",
        json={"token_organizator": token_organizator, "puncte": puncte},
        timeout=15,  # generarea traseului poate dura puțin mai mult
    ))


def sterge_traseu(cod, token_organizator):
    return _trateaza(lambda: requests.delete(
        f"{SERVER_URL}/grupuri/{cod}/traseu",
        json={"token_organizator": token_organizator},
        timeout=TIMEOUT,
    ))


def sterge_grup(cod, token_organizator):
    return _trateaza(lambda: requests.delete(
        f"{SERVER_URL}/grupuri/{cod}",
        json={"token_organizator": token_organizator},
        timeout=TIMEOUT,
    ))
