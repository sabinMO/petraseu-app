[app]
title = Pe Traseu
package.name = petraseu
package.domain = org.petraseu

source.dir = .
source.include_exts = py,png,jpg,kv,atlas
source.include_patterns = assets/markers/*.png,assets/icon.png

icon.filename = %(source.dir)s/assets/icon.png

version = 0.1

requirements = python3,kivy==2.2.1
orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_FINE_LOCATION,ACCESS_COARSE_LOCATION

android.api = 33
android.minapi = 26
android.ndk = 27.3.13750724
android.build_tools_version = 33.0.3
android.accept_sdk_license = True
android.archs = arm64-v8a
android.sdk_path = /usr/local/lib/android/sdk
android.ndk_path = /usr/local/lib/android/sdk/ndk/27.3.13750724
android.ndk_version = 27.3.13750724
android.skip_update = True

[buildozer]
log_level = 2
warn_on_root = 1