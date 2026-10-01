buildozer android debug
adb install -r bin/labtag-1.0-arm64-v8a_armeabi-v7a-debug.apk

adb logcat -c
adb logcat | grep -Ei "LABTAG|QRScanner|mlkit|camera|AndroidRuntime"