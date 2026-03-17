import json

from src.security.key_management import KeyAuthority, MasterKeyRing


def test_master_keyring_bootstrap_encrypts_and_loads(tmp_path):
    bootstrap = "11" * 32
    keyring_path = tmp_path / "master_keyring.enc.json"

    ring = MasterKeyRing(bootstrap_secret_hex=bootstrap, keyring_path=keyring_path)

    assert keyring_path.exists()
    assert ring.get_active_epoch() == 1
    assert ring.get_active_secret_hex() == bootstrap

    envelope = json.loads(keyring_path.read_text(encoding="utf-8"))
    ciphertext = envelope["keys"][0]["ciphertext"]
    # Verify secret is encrypted-at-rest, not plaintext in file
    assert bootstrap not in keyring_path.read_text(encoding="utf-8")
    assert isinstance(ciphertext, str) and len(ciphertext) > 0


def test_master_keyring_rotation_advances_epoch(tmp_path):
    bootstrap = "22" * 32
    rotated = "33" * 32
    keyring_path = tmp_path / "master_keyring.enc.json"

    ring = MasterKeyRing(bootstrap_secret_hex=bootstrap, keyring_path=keyring_path)
    result = ring.rotate(new_secret_hex=rotated)

    assert result["previous_epoch"] == 1
    assert result["new_epoch"] == 2
    assert ring.get_active_epoch() == 2
    assert ring.get_active_secret_hex() == rotated


def test_key_authority_loads_active_rotated_epoch(tmp_path):
    bootstrap = "44" * 32
    rotated = "55" * 32
    keyring_path = tmp_path / "master_keyring.enc.json"

    authority = KeyAuthority(master_secret_hex=bootstrap, keyring_path=keyring_path)
    authority.rotate_master_secret(new_secret_hex=rotated)

    reloaded = KeyAuthority(master_secret_hex=bootstrap, keyring_path=keyring_path)
    assert reloaded.active_epoch == 2
