"""
Muntomani - Aplicație client (Kivy + KivyMD)

Cum funcționează, pe scurt:
- Nu există login. Identitatea ta într-un grup e doar un id generat de server
  când creezi sau te alături unui grup (păstrat în memoria aplicației, NU pe disc).
- La fiecare câteva secunde, aplicația:
    1) trimite poziția GPS curentă către server, și
    2) cere de la server poziția tuturor + mesajele de chat (polling simplu).
- Harta arată traseele montane (tile-uri OpenTopoMap), cu un punct colorat
  și numele fiecărui participant.
- Organizatorul poate șterge grupul oricând; datele dispar de pe server imediat
  (serverul nu salvează nimic pe disc - vezi server/main.py).

Testare pe calculator (fără telefon):
    pip install -r requirements_desktop.txt
    python genereaza_marcatori.py     # o singură dată, generează iconițele
    python main.py
(Pe calculator nu există GPS real, așa că aplicația simulează o poziție
care se mișcă ușor, doar ca să vezi cum arată harta - vezi PORNESTE_SIMULARE_DESKTOP.)
"""

import math
import os
import tempfile
import threading
import urllib.request

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle, RoundedRectangle
from kivy.uix.image import Image as KivyImage
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.metrics import dp

from kivymd.app import MDApp
from kivymd.uix.card import MDCard
from kivymd.uix.dialog import MDDialog
from kivymd.uix.button import MDFlatButton, MDIconButton
from kivymd.uix.label import MDLabel
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.textfield import MDTextField

try:
    from kivymd.toast import toast
except Exception:
    def toast(text):
        pass  # pe unele platforme/versiuni modulul de toast poate lipsi - nu blocăm aplicația

from kivy_garden.mapview import MapView, MapMarker, MapSource, MapLayer

import api

# GPS real, disponibil doar pe Android. Pe calculator, folosim o simulare.
try:
    from plyer import gps
    GPS_DISPONIBIL = True
except Exception:
    GPS_DISPONIBIL = False


# --------------------------------------------------------------------------
# Culorile brandului "Pe Traseu" - aceleași ca în iconița aplicației, ca
# interfața să se simtă unitară cu iconița de pe telefon.
# --------------------------------------------------------------------------
CULOARE_FUNDAL_INCHIS = "#16302B"   # verde-pin închis, fundalul iconiței
CULOARE_FUNDAL_CARD = "#1F3D32"     # un pic mai deschis, pentru carduri pe fundal închis
CULOARE_ACCENT = "#E8A33D"          # auriu - coarda din iconiță, acțiuni principale
CULOARE_ACCENT_DESCHIS = "#F2C14E"  # auriu deschis - pinul din iconiță
CULOARE_TEXT_DESCHIS = "#F4EFE3"    # crem - aceeași culoare ca muntele din iconiță


# --------------------------------------------------------------------------
# Sursa de hartă: OpenTopoMap - hartă topografică gratuită, cu poteci/trasee
# montane vizibile (nu necesită niciun cont sau cheie API).
# --------------------------------------------------------------------------
SURSA_HARTA = MapSource(
    url="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    cache_key="opentopomap",
    min_zoom=2,
    max_zoom=17,
    tile_size=256,
    image_ext="png",
    attribution="(c) OpenTopoMap (CC-BY-SA) (c) OpenStreetMap contributors",
    subdomains="abc",
)

# Coordonate implicite la pornire (Munții Bucegi) - doar pentru a centra harta
# înainte de a primi prima poziție GPS reală.
LAT_IMPLICIT = 45.4097
LON_IMPLICIT = 25.4597


def hex_to_rgb_float(culoare_hex):
    culoare_hex = culoare_hex.lstrip("#")
    r = int(culoare_hex[0:2], 16) / 255
    g = int(culoare_hex[2:4], 16) / 255
    b = int(culoare_hex[4:6], 16) / 255
    return (r, g, b, 1)


class MarcatorParticipant(MapMarker):
    """Un punct colorat pe hartă, cu numele participantului afișat deasupra."""

    def __init__(self, nume, culoare_hex, **kwargs):
        fisier_imagine = f"assets/markers/marker_{culoare_hex.lstrip('#').upper()}.png"
        super().__init__(source=fisier_imagine, **kwargs)
        self.size = (dp(36), dp(36))

        self.eticheta = Label(
            text=nume,
            font_size="13sp",
            bold=True,
            color=(1, 1, 1, 1),
            size_hint=(None, None),
        )
        self.eticheta.texture_update()
        self.eticheta.size = (self.eticheta.texture_size[0] + dp(12), dp(20))

        with self.eticheta.canvas.before:
            Color(0, 0, 0, 0.6)
            self._fundal_eticheta = RoundedRectangle(
                pos=self.eticheta.pos, size=self.eticheta.size, radius=[dp(4)]
            )

        self.eticheta.bind(pos=self._actualizeaza_fundal, size=self._actualizeaza_fundal)
        self.add_widget(self.eticheta)
        self.bind(pos=self._repozitioneaza, size=self._repozitioneaza)
        self._repozitioneaza()

    def _actualizeaza_fundal(self, *args):
        self._fundal_eticheta.pos = self.eticheta.pos
        self._fundal_eticheta.size = self.eticheta.size

    def _repozitioneaza(self, *args):
        self.eticheta.center_x = self.center_x
        self.eticheta.y = self.top + dp(2)


class StratOverlayTrasee(MapLayer):
    """
    Strat transparent deasupra hărții de bază (OpenTopoMap), care afișează
    marcajele de traseu montan: punct roșu, linie albastră, cruce roșie,
    punct galben, bandă etc. - exact ca pe Mapy.cz sau alte aplicații de munte.

    Cum funcționează tehnic:
    - Tile-urile de bază (OpenTopoMap) = topografia terenului, curbe de nivel
    - Tile-urile acestui overlay (waymarkedtrails.org) = PNG-uri transparente
      cu marcajele colorate suprapuse exact pe aceeași grilă de tile-uri
    - La fiecare mișcare/zoom al hărții, reposition() recalculează ce tile-uri
      sunt vizibile și le descarcă dacă nu sunt deja în cache

    Cache local: tile-urile descărcate se salvează în folderul temp al
    sistemului (dispare la repornire, dar economisește trafic în aceeași sesiune).
    """

    URL_TILE = "https://tile.waymarkedtrails.org/hiking/{z}/{x}/{y}.png"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._cache_dir = os.path.join(tempfile.gettempdir(), "petraseu_hiking_overlay")
        os.makedirs(self._cache_dir, exist_ok=True)
        self._texturi = {}          # (z, tx, ty) -> texture Kivy
        self._in_descarcare = set() # (z, tx, ty) care se descarcă acum

    # -------- Conversii matematice tile ↔ lat/lon (standard OSM) --------

    @staticmethod
    def _lat_la_tile_y(lat, zoom):
        n = 2 ** zoom
        rad = math.radians(lat)
        return int((1 - math.log(math.tan(rad) + 1 / math.cos(rad)) / math.pi) / 2 * n)

    @staticmethod
    def _lon_la_tile_x(lon, zoom):
        return int((lon + 180) / 360 * 2 ** zoom)

    @staticmethod
    def _tile_y_la_lat(ty, zoom):
        n = math.pi - 2 * math.pi * ty / 2 ** zoom
        return math.degrees(math.atan(math.sinh(n)))

    @staticmethod
    def _tile_x_la_lon(tx, zoom):
        return tx / 2 ** zoom * 360 - 180

    # -------- Ciclul de viață --------

    def reposition(self):
        """Apelat de MapView la fiecare pan/zoom - redesenăm ce e vizibil."""
        if not self.parent:
            return
        # Amânăm puțin ca MapView să-și termine propria randare mai întâi
        Clock.schedule_once(self._redeseneaza, 0.05)

    def _redeseneaza(self, dt=0):
        self.canvas.clear()
        mapview = self.parent
        if not mapview:
            return

        zoom = int(mapview.zoom)
        # Limităm zoom-ul la ce oferă waymarkedtrails (max 15)
        if zoom > 15:
            zoom = 15

        # Colțurile viewport-ului curent în lat/lon
        try:
            lat_nv, lon_nv = mapview.get_latlon_at(0, mapview.height)
            lat_se, lon_se = mapview.get_latlon_at(mapview.width, 0)
        except Exception:
            return

        # Tile-urile vizibile (cu un tile în plus pe fiecare margine ca buffer)
        tx_min = max(0, self._lon_la_tile_x(lon_nv, zoom) - 1)
        tx_max = self._lon_la_tile_x(lon_se, zoom) + 1
        ty_min = max(0, self._lat_la_tile_y(lat_nv, zoom) - 1)
        ty_max = self._lat_la_tile_y(lat_se, zoom) + 1

        for tx in range(tx_min, tx_max + 1):
            for ty in range(ty_min, ty_max + 1):
                self._randeaza_tile(zoom, tx, ty, mapview)

    def _randeaza_tile(self, z, tx, ty, mapview):
        cheie = (z, tx, ty)

        if cheie in self._texturi:
            # Tile disponibil - calculăm poziția pe ecran și îl desenăm
            lat_nv = self._tile_y_la_lat(ty, z)
            lon_nv = self._tile_x_la_lon(tx, z)
            lat_se = self._tile_y_la_lat(ty + 1, z)
            lon_se = self._tile_x_la_lon(tx + 1, z)

            try:
                x1, y_nv = mapview.get_window_xy_from(lat_nv, lon_nv, z)
                x2, y_se = mapview.get_window_xy_from(lat_se, lon_se, z)
            except Exception:
                return

            largime = abs(x2 - x1)
            inaltime = abs(y_se - y_nv)
            if largime < 1 or inaltime < 1:
                return

            with self.canvas:
                Color(1, 1, 1, 0.92)  # ușor transparent ca să nu acopere complet topografia
                Rectangle(
                    texture=self._texturi[cheie],
                    pos=(x1, min(y_nv, y_se)),
                    size=(largime, inaltime),
                )

        elif cheie not in self._in_descarcare:
            # Tile lipsă - pornim descărcarea în fundal
            self._in_descarcare.add(cheie)
            threading.Thread(
                target=self._descarca_tile,
                args=(z, tx, ty),
                daemon=True,
            ).start()

    def _descarca_tile(self, z, tx, ty):
        """Rulează pe un thread separat - nu blochează UI-ul."""
        url = self.URL_TILE.format(z=z, x=tx, y=ty)
        cale_cache = os.path.join(self._cache_dir, f"{z}_{tx}_{ty}.png")

        try:
            if not os.path.exists(cale_cache):
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "PeTraseu/1.0 Android hiking app Romania"},
                )
                with urllib.request.urlopen(req, timeout=6) as resp:
                    date = resp.read()
                # Tile-urile transparente (fără trasee) sunt mici - le ignorăm
                if len(date) < 150:
                    self._in_descarcare.discard((z, tx, ty))
                    return
                with open(cale_cache, "wb") as f:
                    f.write(date)

            # Încărcăm textura pe thread-ul principal (Kivy e single-threaded pentru OpenGL)
            Clock.schedule_once(lambda dt: self._incarca_textura(z, tx, ty, cale_cache))

        except Exception:
            # Tile indisponibil (offline, eroare rețea) - ignorăm silențios
            self._in_descarcare.discard((z, tx, ty))

    def _incarca_textura(self, z, tx, ty, cale):
        """Rulează pe thread-ul principal - poate accesa OpenGL."""
        try:
            img = CoreImage(cale, ext="png")
            self._texturi[(z, tx, ty)] = img.texture
            # Redesenăm ca să apară tile-ul proaspăt descărcat
            Clock.schedule_once(self._redeseneaza, 0)
        except Exception:
            pass
        finally:
            self._in_descarcare.discard((z, tx, ty))

    def goleste_cache(self):
        """Curăță tile-urile din cache (util dacă schimbi zoom-ul mult)."""
        self._texturi.clear()
        self.canvas.clear()


class StratTraseu(MapLayer):
    """
    Strat desenat peste hartă, care arată linia traseului (generat de server
    pe baza punctelor alese de organizator). Se redesenează automat de fiecare
    dată când harta e mutată sau se schimbă zoom-ul (metoda reposition()),
    altfel linia ar rămâne "lipită" de ecran în loc să urmeze harta.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.puncte = []  # listă de (lat, lon), în ordine

    def seteaza_puncte(self, puncte):
        self.puncte = puncte
        self.reposition()

    def reposition(self):
        self.canvas.clear()
        if len(self.puncte) < 2 or self.parent is None:
            return
        coordonate = []
        for lat, lon in self.puncte:
            x, y = self.parent.get_window_xy_from(lat, lon, self.parent.zoom)
            coordonate += [x, y]
        with self.canvas:
            # contur închis la culoare, ca traseul să iasă în evidență pe orice fundal
            Color(0.09, 0.19, 0.16, 0.9)
            Line(points=coordonate, width=dp(6), joint="round", cap="round")
            Color(0.91, 0.64, 0.24, 1)
            Line(points=coordonate, width=dp(3.5), joint="round", cap="round")


# ----------------------------------- Ecrane -----------------------------------

class EcranAcasa(Screen):
    pass


class EcranCreare(Screen):
    def on_enter(self):
        self.rand_start = RandPunctTraseu("Start traseu (ex: Gara Bușteni)")
        self.rand_final = RandPunctTraseu("Final traseu (ex: Cabana Omu)")
        self.randuri_intermediare = []
        self.ids.eticheta_eroare_creare.text = ""
        self._redeseneaza_puncte()

    def _redeseneaza_puncte(self):
        container = self.ids.container_puncte_traseu
        container.clear_widgets()
        container.add_widget(self.rand_start)

        for rand in self.randuri_intermediare:
            container.add_widget(rand)

        rand_plus = MDBoxLayout(size_hint_y=None, height=dp(44))
        rand_plus.add_widget(MDIconButton(
            icon="plus-circle-outline",
            pos_hint={"center_x": 0.5},
            theme_text_color="Custom",
            text_color=(0.91, 0.64, 0.24, 1),
            on_release=lambda x: self._adauga_intermediar(),
        ))
        container.add_widget(rand_plus)
        container.add_widget(self.rand_final)

    def _adauga_intermediar(self):
        rand = RandPunctTraseu(
            f"Punct intermediar {len(self.randuri_intermediare) + 1}",
            poate_fi_sters=True,
            pe_sterge=self._sterge_intermediar,
        )
        self.randuri_intermediare.append(rand)
        self._redeseneaza_puncte()

    def _sterge_intermediar(self, rand):
        self.randuri_intermediare.remove(rand)
        self._redeseneaza_puncte()

    def puncte_traseu(self):
        """Returnează lista de puncte dacă start și final sunt completate, altfel None."""
        if not self.rand_start.are_punct_valid() or not self.rand_final.are_punct_valid():
            return None
        puncte = [{"lat": self.rand_start.lat, "lon": self.rand_start.lon}]
        for rand in self.randuri_intermediare:
            if rand.are_punct_valid():
                puncte.append({"lat": rand.lat, "lon": rand.lon})
        puncte.append({"lat": self.rand_final.lat, "lon": self.rand_final.lon})
        return puncte


class EcranAlaturare(Screen):
    pass


class RandPunctTraseu(MDBoxLayout):
    """
    Un rând din formularul de traseu: un câmp de text în care organizatorul
    scrie un nume de loc (ex: "Cabana Babele"), cu sugestii care apar pe
    măsură ce scrie (căutare cu mică întârziere, ca să nu trimitem o cerere
    la fiecare literă) - similar cu căutarea din Mapy.cz. Punctele
    intermediare au și un buton de ștergere (X); Start/Final nu.
    """

    def __init__(self, eticheta, poate_fi_sters=False, pe_sterge=None, **kwargs):
        super().__init__(orientation="vertical", size_hint_y=None, spacing=dp(2), **kwargs)
        self.lat = None
        self.lon = None
        self._cronometru_cautare = None
        self._selectie_in_curs = False

        rand_camp = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(56))
        self.camp = MDTextField(hint_text=eticheta)
        self.camp.bind(text=self._la_schimbare_text)
        rand_camp.add_widget(self.camp)

        rand_camp.add_widget(MDIconButton(
            icon="crosshairs-gps",
            size_hint_x=None,
            width=dp(40),
            on_release=lambda x: self._foloseste_locatia_mea(),
        ))

        if poate_fi_sters:
            rand_camp.add_widget(MDIconButton(
                icon="close",
                size_hint_x=None,
                width=dp(40),
                on_release=lambda x: pe_sterge(self) if pe_sterge else None,
            ))

        self.lista_sugestii = MDBoxLayout(orientation="vertical", size_hint_y=None, height=0)

        self.add_widget(rand_camp)
        self.add_widget(self.lista_sugestii)
        self.height = self.minimum_height
        self.bind(minimum_height=self.setter("height"))

    def are_punct_valid(self):
        return self.lat is not None and self.lon is not None

    def _foloseste_locatia_mea(self):
        app = MDApp.get_running_app()
        if app.lat_proprie is None or app.lon_proprie is None:
            toast("Nu am încă locația ta. Mergi puțin pe ecranul hărții, apoi revino aici.")
            return
        self._selectie_in_curs = True
        self.camp.text = "Locația mea actuală"
        self._selectie_in_curs = False
        self.lat = app.lat_proprie
        self.lon = app.lon_proprie
        self.lista_sugestii.clear_widgets()
        self.lista_sugestii.height = 0

    def _la_schimbare_text(self, instance, text):
        if self._selectie_in_curs:
            return
        self.lat = None
        self.lon = None
        if self._cronometru_cautare:
            Clock.unschedule(self._cronometru_cautare)
        if len(text.strip()) < 3:
            self._afiseaza_sugestii([])
            return
        self._cronometru_cautare = Clock.schedule_once(lambda dt: self._cauta(text), 0.6)

    def _cauta(self, text):
        def cere():
            try:
                rezultate = api.cauta_locatie(text)
            except api.EroareRetea:
                rezultate = []
            Clock.schedule_once(lambda dt: self._afiseaza_sugestii(rezultate))

        threading.Thread(target=cere, daemon=True).start()

    def _afiseaza_sugestii(self, rezultate):
        self.lista_sugestii.clear_widgets()
        rezultate = rezultate[:5]
        for rezultat in rezultate:
            self.lista_sugestii.add_widget(MDFlatButton(
                text=rezultat["nume"][:60],
                size_hint_y=None,
                height=dp(34),
                halign="left",
                on_release=lambda x, r=rezultat: self._alege(r),
            ))
        self.lista_sugestii.height = dp(34) * len(rezultate)

    def _alege(self, rezultat):
        self._selectie_in_curs = True
        self.camp.text = rezultat["nume"][:60]
        self._selectie_in_curs = False
        self.lat = rezultat["lat"]
        self.lon = rezultat["lon"]
        self.lista_sugestii.clear_widgets()
        self.lista_sugestii.height = 0


class EcranEditareTraseu(Screen):
    """Permite organizatorului să seteze/modifice traseul după crearea grupului."""

    def on_enter(self):
        self.rand_start = RandPunctTraseu("Start traseu (ex: Gara Bușteni)")
        self.rand_final = RandPunctTraseu("Final traseu (ex: Cabana Omu)")
        self.randuri_intermediare = []
        self.ids.eticheta_eroare_et.text = ""
        self._redeseneaza_puncte()

    def _redeseneaza_puncte(self):
        container = self.ids.container_puncte_et
        container.clear_widgets()
        container.add_widget(self.rand_start)
        for rand in self.randuri_intermediare:
            container.add_widget(rand)
        rand_plus = MDBoxLayout(size_hint_y=None, height=dp(44))
        rand_plus.add_widget(MDIconButton(
            icon="plus-circle-outline",
            pos_hint={"center_x": 0.5},
            theme_text_color="Custom",
            text_color=(0.91, 0.64, 0.24, 1),
            on_release=lambda x: self._adauga_intermediar(),
        ))
        container.add_widget(rand_plus)
        container.add_widget(self.rand_final)

    def _adauga_intermediar(self):
        rand = RandPunctTraseu(
            f"Punct intermediar {len(self.randuri_intermediare) + 1}",
            poate_fi_sters=True,
            pe_sterge=self._sterge_intermediar,
        )
        self.randuri_intermediare.append(rand)
        self._redeseneaza_puncte()

    def _sterge_intermediar(self, rand):
        self.randuri_intermediare.remove(rand)
        self._redeseneaza_puncte()

    def salveaza_traseul(self):
        if not self.rand_start.are_punct_valid() or not self.rand_final.are_punct_valid():
            self.ids.eticheta_eroare_et.text = "Alege Start și Final din sugestiile afișate."
            return
        puncte = [{"lat": self.rand_start.lat, "lon": self.rand_start.lon}]
        for rand in self.randuri_intermediare:
            if rand.are_punct_valid():
                puncte.append({"lat": rand.lat, "lon": rand.lon})
        puncte.append({"lat": self.rand_final.lat, "lon": self.rand_final.lon})
        self.ids.eticheta_eroare_et.text = "Se generează traseul..."
        app = MDApp.get_running_app()

        def cere():
            try:
                api.seteaza_traseu(app.cod_grup, app.token_organizator, puncte)
                Clock.schedule_once(lambda dt: app.deschide_ecran("harta"))
            except api.EroareRetea as e:
                Clock.schedule_once(lambda dt: setattr(self.ids.eticheta_eroare_et, "text", str(e)))

        threading.Thread(target=cere, daemon=True).start()


class EcranHarta(Screen):
    def on_enter(self):
        app = MDApp.get_running_app()
        self._marcatori_pe_harta = []
        self._centrat_initial = False
        self._traseu_curent = None  # ca să nu redesenăm degeaba la fiecare interogare

        # construim harta din Python (ca să putem seta sursa OpenTopoMap)
        self.harta = MapView(
            map_source=SURSA_HARTA,
            lat=LAT_IMPLICIT,
            lon=LON_IMPLICIT,
            zoom=12,
        )
        self.ids.container_harta.add_widget(self.harta)

        # Strat 1: marcajele de traseu (punct roșu, linie albastră, cruce roșie etc.)
        # - tile-uri transparente de la waymarkedtrails.org, suprapuse peste OpenTopoMap
        self.overlay_trasee = StratOverlayTrasee()
        self.harta.add_layer(self.overlay_trasee, mode="window")

        # Strat 2: traseul grupului (linia aurie desenată de organizator)
        self.strat_traseu = StratTraseu()
        self.harta.add_layer(self.strat_traseu, mode="window")

        self.ids.eticheta_cod_grup.text = f"Cod grup: {app.cod_grup}"
        self.ids.bara_harta.title = app.nume_grup

        # doar organizatorul vede iconițele de "setează traseu" și "șterge grup"
        iconite_dreapta = [
            ["chat", lambda x: app.deschide_ecran("chat")],
            ["paw", lambda x: app.buton_urs()],
        ]
        if app.token_organizator:
            iconite_dreapta.append(["map-marker-path", lambda x: app.deschide_ecran("editare_traseu")])
            iconite_dreapta.append(["delete", lambda x: app.confirma_stergere_grup()])
        self.ids.bara_harta.right_action_items = iconite_dreapta

        # bara de editare traseu - vizibilă doar pentru organizator
        if app.token_organizator:
            self.ids.bara_editare_traseu.height = dp(40)

        self._porneste_gps()
        Clock.schedule_interval(self._actualizeaza_din_server, 5)
        self._actualizeaza_din_server(0)  # o primă cerere imediată

    def on_leave(self):
        Clock.unschedule(self._actualizeaza_din_server)
        self._opreste_gps()
        self.ids.container_harta.clear_widgets()

    # ---------- GPS (real pe Android, simulat pe calculator) ----------

    def _porneste_gps(self):
        if GPS_DISPONIBIL:
            try:
                gps.configure(on_location=self._pe_locatie_gps, on_status=lambda *a: None)
                gps.start(minTime=3000, minDistance=5)
                return
            except NotImplementedError:
                pass  # ex: rulezi pe calculator, GPS-ul nu există -> simulăm
        self._porneste_simulare_desktop()

    def _opreste_gps(self):
        if GPS_DISPONIBIL:
            try:
                gps.stop()
            except Exception:
                pass
        Clock.unschedule(self._pas_simulare_desktop)

    def _pe_locatie_gps(self, **kwargs):
        lat = kwargs.get("lat")
        lon = kwargs.get("lon")
        if lat is None or lon is None:
            return
        self._am_primit_locatie(lat, lon)

    def _porneste_simulare_desktop(self):
        # NUMAI pentru testare pe calculator, unde nu există GPS real.
        self._lat_sim = LAT_IMPLICIT
        self._lon_sim = LON_IMPLICIT
        Clock.schedule_interval(self._pas_simulare_desktop, 4)
        self._pas_simulare_desktop(0)

    def _pas_simulare_desktop(self, dt):
        import random
        self._lat_sim += random.uniform(-0.0006, 0.0006)
        self._lon_sim += random.uniform(-0.0006, 0.0006)
        self._am_primit_locatie(self._lat_sim, self._lon_sim)

    def _am_primit_locatie(self, lat, lon):
        app = MDApp.get_running_app()
        app.lat_proprie = lat
        app.lon_proprie = lon

        def trimite():
            try:
                api.trimite_locatie(app.cod_grup, app.id_membru, lat, lon)
            except api.EroareRetea:
                pass  # actualizare de fundal - ignorăm erorile trecătoare

        threading.Thread(target=trimite, daemon=True).start()

    # ---------- Interogare periodică server (pozițiile tuturor) ----------

    def _actualizeaza_din_server(self, dt):
        app = MDApp.get_running_app()

        def cere():
            try:
                date = api.stare_grup(app.cod_grup)
                Clock.schedule_once(lambda d: self._aplica_stare(date))
            except api.EroareRetea:
                pass

        threading.Thread(target=cere, daemon=True).start()

    def _aplica_stare(self, date):
        for marcator in self._marcatori_pe_harta:
            self.harta.remove_marker(marcator)
        self._marcatori_pe_harta = []

        app = MDApp.get_running_app()
        for membru in date.get("membri", []):
            if membru["lat"] is None or membru["lon"] is None:
                continue
            marcator = MarcatorParticipant(
                nume=membru["nume"],
                culoare_hex=membru["culoare"],
                lat=membru["lat"],
                lon=membru["lon"],
            )
            self.harta.add_marker(marcator)
            self._marcatori_pe_harta.append(marcator)

        if not self._centrat_initial and app.lat_proprie is not None:
            self.harta.center_on(app.lat_proprie, app.lon_proprie)
            self._centrat_initial = True

        self._actualizeaza_legenda(date.get("membri", []))
        self._aplica_traseu(date.get("traseu"))
        self._aplica_alerta_urs(date.get("alerta_urs"))

    def _aplica_alerta_urs(self, alerta):
        bara = self.ids.get("bara_alerta_urs")
        if not bara:
            return
        if alerta:
            bara.height = dp(48)
            self.ids.text_alerta_urs.text = f"⚠️  ATENȚIE: Urs raportat de {alerta['raportat_de']}!"
        else:
            bara.height = 0

    def _aplica_traseu(self, traseu):
        linie_noua = traseu["linie"] if traseu else None
        if linie_noua == self._traseu_curent:
            return  # nu s-a schimbat nimic față de ultima dată - nu redesenăm degeaba
        self._traseu_curent = linie_noua
        puncte = [(p["lat"], p["lon"]) for p in linie_noua] if linie_noua else []
        self.strat_traseu.seteaza_puncte(puncte)

    def _actualizeaza_legenda(self, membri):
        container = self.ids.legenda_participanti
        container.clear_widgets()
        for membru in membri:
            rand = MDBoxLayout(
                orientation="horizontal",
                size_hint=(None, None),
                size=(dp(110), dp(28)),
                spacing=dp(6),
            )
            buline = MDBoxLayout(
                size_hint=(None, None),
                size=(dp(14), dp(14)),
                md_bg_color=hex_to_rgb_float(membru["culoare"]),
                radius=[dp(7)],
            )
            eticheta = MDLabel(
                text=membru["nume"],
                font_style="Caption",
                size_hint_x=None,
                width=dp(85),
            )
            rand.add_widget(buline)
            rand.add_widget(eticheta)
            container.add_widget(rand)


class EcranChat(Screen):
    def on_enter(self):
        self.ids.container_mesaje.clear_widgets()
        Clock.schedule_interval(self._actualizeaza_mesaje, 4)
        self._actualizeaza_mesaje(0)

    def on_leave(self):
        Clock.unschedule(self._actualizeaza_mesaje)

    def _actualizeaza_mesaje(self, dt):
        app = MDApp.get_running_app()

        def cere():
            try:
                date = api.stare_grup(app.cod_grup)
                Clock.schedule_once(lambda d: self._afiseaza_mesaje(date.get("mesaje", [])))
            except api.EroareRetea:
                pass

        threading.Thread(target=cere, daemon=True).start()

    def _afiseaza_mesaje(self, mesaje):
        container = self.ids.container_mesaje
        container.clear_widgets()
        for mesaj in mesaje:
            card = MDCard(
                orientation="vertical",
                size_hint=(0.86, None),
                padding=(dp(12), dp(8)),
                spacing=dp(2),
                radius=[dp(2), dp(14), dp(14), dp(14)],
                md_bg_color=CULOARE_FUNDAL_CARD,
                line_color=hex_to_rgb_float(mesaj["culoare"]),
                line_width=dp(1.4),
                elevation=0,
            )
            nume_eticheta = MDLabel(
                text=mesaj["nume"],
                bold=True,
                size_hint_y=None,
                height=dp(20),
                theme_text_color="Custom",
                text_color=hex_to_rgb_float(mesaj["culoare"]),
                font_style="Caption",
            )
            text_eticheta = MDLabel(
                text=mesaj["text"],
                size_hint_y=None,
                adaptive_height=True,
                theme_text_color="Custom",
                text_color=(0.96, 0.96, 0.94, 1),
            )
            card.add_widget(nume_eticheta)
            card.add_widget(text_eticheta)
            card.height = card.minimum_height
            card.bind(minimum_height=card.setter("height"))

            rand = MDBoxLayout(size_hint_y=None, padding=(0, dp(2)))
            rand.height = card.height + dp(4)
            card.bind(height=lambda inst, val, r=rand: setattr(r, "height", val + dp(4)))
            rand.add_widget(card)
            container.add_widget(rand)

        # derulează automat la ultimul mesaj
        Clock.schedule_once(lambda dt: setattr(self.ids.derulare_mesaje, "scroll_y", 0), 0.1)


# ----------------------------------- Aplicația -----------------------------------

class MuntomaniApp(MDApp):
    cod_grup = None
    id_membru = None
    token_organizator = None  # None dacă nu ești organizator
    nume_grup = ""
    culoare_proprie = "#1E88E5"
    lat_proprie = None
    lon_proprie = None

    def build(self):
        self.theme_cls.primary_palette = "Green"
        self.theme_cls.theme_style = "Dark"
        self.title = "Pe Traseu"
        # root-ul (ScreenManager) se încarcă automat din muntomani.kv
        return None

    def deschide_ecran(self, nume_ecran):
        self.root.current = nume_ecran

    def iesi_din_aplicatie(self):
        """Închide aplicația complet (pe Android, închide activitatea)."""
        self.stop()

    def buton_urs(self):
        """Dialogul 1: 'This is a joke' cu Yes/No"""
        self.dialog = MDDialog(
            title="🐻 Bear Alert",
            text="This is a joke.",
            buttons=[
                MDFlatButton(
                    text="YES",
                    on_release=lambda x: self._urs_yes(),
                ),
                MDFlatButton(
                    text="NO",
                    theme_text_color="Custom",
                    text_color=(0.91, 0.64, 0.24, 1),
                    on_release=lambda x: self._urs_no(),
                ),
            ],
        )
        self.dialog.open()

    def _urs_yes(self):
        """Utilizatorul confirmă că e o glumă - primește mesajul special"""
        self.dialog.dismiss()
        self.dialog = MDDialog(
            title="😈",
            text="I hope you will die soon.",
            buttons=[
                MDFlatButton(
                    text="OK",
                    on_release=lambda x: self.dialog.dismiss(),
                ),
            ],
        )
        self.dialog.open()

    def _urs_no(self):
        """Utilizatorul confirmă că e urs real - alertează tot grupul"""
        self.dialog.dismiss()

        def trimite():
            try:
                api.raporteaza_urs(self.cod_grup, self.id_membru)
            except api.EroareRetea:
                pass

        threading.Thread(target=trimite, daemon=True).start()

    def anuleaza_alerta_urs(self):
        def trimite():
            try:
                api.sterge_alerta_urs(self.cod_grup, self.id_membru)
            except api.EroareRetea:
                pass
        threading.Thread(target=trimite, daemon=True).start()

    def copiaza_cod_grup(self):
        if self.cod_grup:
            Clipboard.copy(self.cod_grup)
            toast("Cod copiat!")

    # ---------------------------- Creare grup ----------------------------

    def creeaza_grup(self):
        ecran = self.root.get_screen("creare")
        nume_grup = ecran.ids.camp_nume_grup.text.strip()
        nume_organizator = ecran.ids.camp_nume_organizator.text.strip()

        if not nume_grup or not nume_organizator:
            ecran.ids.eticheta_eroare_creare.text = "Completează numele grupului și numele tău."
            return

        ecran.ids.eticheta_eroare_creare.text = "Se creează grupul..."
        puncte_traseu = ecran.puncte_traseu()  # None dacă nu s-a completat traseul

        def cere():
            try:
                date = api.creeaza_grup(nume_grup, nume_organizator)
                Clock.schedule_once(lambda dt: self._grup_creat(date, nume_grup, puncte_traseu))
            except api.EroareRetea as e:
                Clock.schedule_once(lambda dt: setattr(ecran.ids.eticheta_eroare_creare, "text", str(e)))

        threading.Thread(target=cere, daemon=True).start()

    def _grup_creat(self, date, nume_grup, puncte_traseu):
        self.cod_grup = date["cod_grup"]
        self.id_membru = date["id_membru"]
        self.token_organizator = date["token_organizator"]
        self.culoare_proprie = date["culoare"]
        self.nume_grup = nume_grup

        if puncte_traseu:
            # trimitem traseul în fundal, fără să blocăm intrarea pe hartă
            def trimite_traseu():
                try:
                    api.seteaza_traseu(self.cod_grup, self.token_organizator, puncte_traseu)
                except api.EroareRetea:
                    pass
            threading.Thread(target=trimite_traseu, daemon=True).start()

        self.deschide_ecran("harta")

    # ---------------------------- Alăturare grup ----------------------------

    def alatura_grup(self):
        ecran = self.root.get_screen("alaturare")
        cod = ecran.ids.camp_cod.text.strip().upper()
        nume = ecran.ids.camp_nume_alaturare.text.strip()

        if not cod or not nume:
            ecran.ids.eticheta_eroare_alaturare.text = "Completează ambele câmpuri."
            return

        ecran.ids.eticheta_eroare_alaturare.text = "Se trimite cererea..."

        def cere():
            try:
                date = api.alatura_grup(cod, nume)
                Clock.schedule_once(lambda dt: self._alaturat_cu_succes(date, cod))
            except api.EroareRetea as e:
                Clock.schedule_once(lambda dt: setattr(ecran.ids.eticheta_eroare_alaturare, "text", str(e)))

        threading.Thread(target=cere, daemon=True).start()

    def _alaturat_cu_succes(self, date, cod):
        self.cod_grup = cod
        self.id_membru = date["id_membru"]
        self.token_organizator = None  # nu ești organizator
        self.culoare_proprie = date["culoare"]
        self.nume_grup = date["nume_grup"]
        self.deschide_ecran("harta")

    # ---------------------------- Chat ----------------------------

    def trimite_mesaj_chat(self):
        ecran = self.root.get_screen("chat")
        text = ecran.ids.camp_mesaj.text.strip()
        if not text:
            return
        ecran.ids.camp_mesaj.text = ""

        def cere():
            try:
                api.trimite_mesaj(self.cod_grup, self.id_membru, text)
            except api.EroareRetea:
                pass

        threading.Thread(target=cere, daemon=True).start()

    # ---------------------------- Ieșire / ștergere grup ----------------------------

    def confirma_iesire(self):
        if self.token_organizator:
            # Organizatorul nu poate "ieși" - doar poate șterge grupul.
            self.dialog = MDDialog(
                title="Ești organizatorul grupului",
                text="Nu poți ieși din grup - îl poți doar șterge, cu iconița de coș de gunoi din dreapta sus. Cât timp ții aplicația deschisă, ceilalți te văd pe hartă.",
                buttons=[
                    MDFlatButton(text="AM ÎNȚELES", on_release=lambda x: self.dialog.dismiss()),
                ],
            )
            self.dialog.open()
            return

        self.dialog = MDDialog(
            title="Ieși din grup?",
            text="Sigur vrei să ieși din acest grup?",
            buttons=[
                MDFlatButton(text="ÎNAPOI", on_release=lambda x: self.dialog.dismiss()),
                MDFlatButton(text="IEȘI", on_release=lambda x: self._iesi_din_grup()),
            ],
        )
        self.dialog.open()

    def _iesi_din_grup(self):
        self.dialog.dismiss()
        if self.token_organizator:
            return  # organizatorul nu poate "ieși" - trebuie să șteargă grupul

        def cere():
            try:
                api.paraseste_grup(self.cod_grup, self.id_membru)
            except api.EroareRetea:
                pass

        threading.Thread(target=cere, daemon=True).start()
        self._reseteaza_stare()
        self.deschide_ecran("acasa")

    def confirma_stergere_grup(self):
        if not self.token_organizator:
            return  # doar organizatorul poate șterge

        self.dialog = MDDialog(
            title="Ștergi grupul?",
            text="Toți participanții vor fi scoși din grup. Nu se poate anula.",
            buttons=[
                MDFlatButton(text="ANULEAZĂ", on_release=lambda x: self.dialog.dismiss()),
                MDFlatButton(text="ȘTERGE", on_release=lambda x: self._sterge_grup()),
            ],
        )
        self.dialog.open()

    def _sterge_grup(self):
        self.dialog.dismiss()
        cod = self.cod_grup
        token = self.token_organizator

        def cere():
            try:
                api.sterge_grup(cod, token)
            except api.EroareRetea:
                pass

        threading.Thread(target=cere, daemon=True).start()
        self._reseteaza_stare()
        self.deschide_ecran("acasa")

    def _reseteaza_stare(self):
        self.cod_grup = None
        self.id_membru = None
        self.token_organizator = None
        self.nume_grup = ""
        self.lat_proprie = None
        self.lon_proprie = None


if __name__ == "__main__":
    MuntomaniApp().run()
