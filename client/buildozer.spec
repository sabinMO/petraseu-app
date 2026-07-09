[app]
title = Pe Traseu
package.name = petraseu
package.domain = org.petraseu

source.dir = .
source.include_exts = py,png,jpg,kv,atlas
source.include_patterns = assets/markers/*.png,assets/icon.png

icon.filename = %(source.dir)s/assets/icon.png

version = 0.1

requirements = python3,kivy,https://github.com/kivymd/KivyMD/archive/master.zip,materialyoucolor,plyer,requests
orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION,ACCESS_NETWORK_STATE
android.api = 33
android.minapi = 26
android.ndk = 25b
android.archs = arm64-v8a
p4a.python_version = 3.10

[buildozer]
log_level = 2
warn_on_root = 1