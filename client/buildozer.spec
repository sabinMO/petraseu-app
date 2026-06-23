[app]
title = Pe Traseu
package.name = petraseu
package.domain = org.petraseu

source.dir = .
source.include_exts = py,png,jpg,kv,atlas
source.include_patterns = assets/markers/*.png,assets/icon.png

icon.filename = %(source.dir)s/assets/icon.png

version = 0.1

# IMPORTANT: kivy_garden.mapview e cel mai sensibil pachet de aici la build.
# Dacă apar erori legate de el, vezi secțiunea "Probleme frecvente" din README.md.
requirements = python3,kivy==2.2.1,kivymd==1.1.1,plyer,requests,kivy_garden.mapview,certifi,urllib3,idna,charset_normalizer
orientation = portrait
fullscreen = 0

# Permisiuni necesare: internet (pentru server) + locație (pentru hartă)
android.permissions = INTERNET,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION

android.api = 33
android.minapi = 26
android.ndk = 25b
android.build_tools_version = 33.0.3
android.accept_sdk_license = True
android.archs = arm64-v8a
[buildozer]
log_level = 2
warn_on_root = 1

