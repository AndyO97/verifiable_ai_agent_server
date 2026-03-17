"""
Master secret key rotation CLI.

Usage:
    python -m src.tools.key_rotation_cli status
    python -m src.tools.key_rotation_cli rotate
"""

import typer

from src.config import get_settings
from src.security.key_management import KeyAuthority

app = typer.Typer(help="Manage encrypted master key rotation")


def _build_authority() -> KeyAuthority:
    settings = get_settings()
    if not settings.security.master_secret_key:
        raise typer.BadParameter(
            "SECURITY_MASTER_SECRET_KEY is not configured. "
            "Set it in .env to enable encrypted key rotation."
        )
    return KeyAuthority(master_secret_hex=settings.security.master_secret_key)


@app.command()
def status() -> None:
    """Show active key epoch and MPK metadata."""
    authority = _build_authority()
    mpk = authority.export_mpk()

    typer.echo(f"Active epoch: {authority.active_epoch}")
    typer.echo(f"Curve: {mpk['curve']}")
    typer.echo(f"Group: {mpk['group']}")


@app.command()
def rotate() -> None:
    """Rotate to a fresh master secret (new active epoch)."""
    authority = _build_authority()
    result = authority.rotate_master_secret()

    typer.echo("Master key rotated successfully")
    typer.echo(f"Previous epoch: {result['previous_epoch']}")
    typer.echo(f"New epoch: {result['new_epoch']}")
    typer.echo(f"Keyring path: {result['keyring_path']}")


if __name__ == "__main__":
    app()
