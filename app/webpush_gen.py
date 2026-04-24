"""CLI helper: print a fresh VAPID key pair ready to paste into .env."""
from .webpush import generate_keypair


def main() -> None:
    priv, pub = generate_keypair()
    print("VAPID_PRIVATE_KEY=" + priv)
    print("VAPID_PUBLIC_KEY=" + pub)


if __name__ == "__main__":
    main()
