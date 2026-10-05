set -eu
apt-get update
apt-get install -y python-cryptography
python -c 'import cryptography; print("NATIVE_CRYPTOGRAPHY="+cryptography.__version__)'
