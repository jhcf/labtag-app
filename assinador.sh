source release.local.env

BUILD_TOOLS=$(ls -d ~/.buildozer/android/platform/android-sdk/build-tools/*/ | tail -1)

# alinhar
${BUILD_TOOLS}zipalign -v 4 \
  bin/labtag-1.0-arm64-v8a_armeabi-v7a-release-unsigned.apk \
  bin/labtag-release-alinhado.apk

# assinar
${BUILD_TOOLS}apksigner sign --ks redemais-release.keystore \
  --out bin/labtag-release-assinado.apk \
  bin/labtag-release-alinhado.apk