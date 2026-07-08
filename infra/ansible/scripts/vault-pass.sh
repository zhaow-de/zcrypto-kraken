#!/usr/bin/env bash
exec /home/zhaow/go/bin/sops -d --extract '["vault_password"]' "$(dirname "$0")/../vault-password.sops.yaml"
