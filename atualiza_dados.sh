echo "ORIGINAL:"
sha256sum dados.json

echo
echo "CÓPIAS NO BUILD:"
find .buildozer -type f -name dados.json -exec sha256sum {} \;