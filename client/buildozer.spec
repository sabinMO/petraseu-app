[app]
title = Pe Traseu
package.name = petraseu
package.domain = org.petraseu

source.dir = .
source.include_exts = py,png,jpg,kv,atlas
source.include_patterns = assets/markers/*.png,assets/icon.png

icon.filename = %(source.dir)s/assets/icon.png

version = 0.1

<<<<<<< HEAD
=======
requirements = python3,kivy==2.2.1,kivymd==1.1.1,plyer,requests,certifi,urllib3,idna,charset_normalizer
>>>>>>> 81e01fe34dca80a6e42d262f6b3407bb057ab0e5

requirements = python3,kivy==2.2.1,kivymd==1.1.1,plyer,requests==2.28.2,certifi,urllib3==1.26.18,idna,charset_normalizer
orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,ACCESS_NETWORK_STATE
android.api = 33
android.minapi = 26
android.ndk = 25b
android.archs = arm64-v8a
p4a.python_version = 3.11
[buildozer]
log_level = 2
warn_on_root = 1
