# Muntomani

Aplicație pentru grupuri de drumeție montană: organizatorul creează un grup,
ceilalți se alătură cu un cod, fiecare apare pe hartă cu un punct colorat și
numele lui, plus un chat de grup. Fără login. Grupul există cât timp vrea
organizatorul - când îl șterge, toate datele dispar (nimic nu e salvat permanent).

## Structura proiectului

```
muntomani/
├── server/                  -> rulează pe internet, ține datele LIVE în memorie
│   ├── main.py
│   └── requirements.txt
└── client/                  -> aplicația de pe telefon
    ├── main.py
    ├── api.py                -> comunicarea cu serverul
    ├── muntomani.kv           -> interfața grafică
    ├── genereaza_marcatori.py -> generează punctele colorate (deja generate)
    ├── assets/markers/*.png   -> punctele colorate, gata făcute
    ├── buildozer.spec         -> rețeta de compilare pentru Android
    ├── requirements_desktop.txt
```

## Pasul 1 - Testează pe calculator (recomandat înainte de telefon)

Ai nevoie de Python 3.10 sau 3.11 instalat.

**A. Pornește serverul** (într-un terminal):
```
cd server
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
Lasă acest terminal deschis. Verifică în browser: `http://127.0.0.1:8000` -
ar trebui să vezi `{"stare":"ok","grupuri_active":0}`.

**B. Pornește aplicația** (în alt terminal):
```
cd client
pip install -r requirements_desktop.txt
python main.py
```
Pe calculator nu există GPS, așa că aplicația simulează o poziție care se
mișcă ușor lângă Bucegi, doar ca să vezi cum arată harta și marcatorii.
Poți deschide aplicația de două ori (din două terminale) ca să simulezi
doi participanți diferiți în același grup.

## Pasul 2 - Pune serverul online (necesar pentru telefoane reale)

Telefoanele nu pot ajunge la `127.0.0.1` de pe calculatorul tău, așa că
serverul trebuie găzduit undeva. Cea mai simplă variantă gratuită:

1. Pune folderul `server/` într-un repo GitHub.
2. Creează cont pe [Render.com](https://render.com) (are plan gratuit).
3. „New Web Service" -> conectezi repo-ul -> Render detectează Python.
4. Build command: `pip install -r requirements.txt`
   Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Render îți dă o adresă de tipul `https://muntomani-server.onrender.com`.

**Important:** planurile gratuite "adorm" serverul după inactivitate -
prima cerere după o pauză lungă poate dura ~30 de secunde. Pentru o tură
reală de o zi, e suficient (serverul rămâne treaz cât timp aplicația trimite
cereri la fiecare câteva secunde).

Apoi deschide `client/api.py` și înlocuiește:
```python
SERVER_URL = "http://127.0.0.1:8000"
```
cu adresa reală, de exemplu:
```python
SERVER_URL = "https://muntomani-server.onrender.com"
```

## Pasul 3 - Compilează APK-ul pentru Android

Buildozer funcționează doar pe Linux (sau WSL pe Windows, sau o mașină
virtuală Linux). Pe Mac/Windows direct nu merge nativ.

```
pip install buildozer cython
cd client
buildozer android debug
```

Prima compilare durează mult (descarcă Android SDK/NDK, 20-40 minute).
APK-ul rezultat apare în `client/bin/muntomani-0.1-debug.apk` - îl copiezi
pe telefon și îl instalezi (trebuie permisă instalarea din surse necunoscute).

## Cum se folosește aplicația

1. **Organizatorul** apasă „Creează un grup nou", scrie un nume pentru grup
   și numele lui -> primește un **cod de grup** (afișat jos pe ecranul hărții).
2. Organizatorul trimite codul celorlalți (WhatsApp, SMS, verbal).
3. **Fiecare participant** apasă „Alătură-te unui grup existent", introduce
   codul + numele lui.
4. La intrarea pe ecranul hărții, aplicația cere automat permisiunea de
   locație și începe să trimită poziția la fiecare câteva secunde.
5. Fiecare apare pe hartă cu un punct de altă culoare și numele lui deasupra.
6. Iconița de chat din dreapta sus duce la discuția de grup.
7. Organizatorul poate șterge grupul oricând (iconița de coș de gunoi) -
   toți sunt scoși și datele dispar definitiv de pe server.

## Probleme frecvente

- **Harta nu arată trasee montane clar la orice nivel de zoom** - asta ține
  de tile-urile OpenTopoMap (gratuite); la zoom foarte mare uneori sunt mai
  încărcate. E folosit fiindcă e gratuit și fără cont; alternativă cu mai
  multe detalii: servicii plătite ca Thunderforest Outdoors (necesită cheie API).
- **`kivy_garden.mapview` dă erori la `buildozer android debug`** - e cel mai
  sensibil pachet din proiect la compilare. Dacă pică build-ul, caută eroarea
  exactă pe [GitHub-ul kivy-garden/mapview](https://github.com/kivy-garden/mapview)
  - de obicei se rezolvă fixând o versiune anume în `requirements` din
  `buildozer.spec`.
- **Aplicația nu vede locații actualizate ale celorlalți** - verifică să fie
  toți conectați la internet și că `SERVER_URL` din `api.py` e adresa corectă,
  pusă online (nu `127.0.0.1`).
- **Pe Android 10+** s-ar putea să fie nevoie și de permisiunea de locație
  „mereu" (background) dacă vrei ca trimiterea poziției să continue cu telefonul
  blocat - asta necesită configurare suplimentară în `buildozer.spec`
  (`android.permissions` cu `ACCESS_BACKGROUND_LOCATION`) și un serviciu Android
  rulând pe fundal, care nu e inclus în acest prim draft.

## Idei de îmbunătățit ulterior

- Notificare/sunet când vine un mesaj nou de chat.
- Trasee predefinite desenate pe hartă (linie), nu doar poziții live.
- Distanță/timp estimat până la următorul participant.
- Buton „trimite alarmă" pentru urgențe, vizibil tuturor instant.
