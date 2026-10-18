import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if os.environ.get("VERCEL"):
    DB_PATH = Path("/tmp/zts_store.db")
else:
    DB_PATH = BASE_DIR / "data" / "zts_store.db"

# Server Configuration
PORT = int(os.environ.get("PORT", 8000))
HOST = os.environ.get("HOST", "0.0.0.0")
SECRET_KEY = os.environ.get("SECRET_KEY", "zesha-super-secret-key-2026")
ADMIN_PIN = os.environ.get("ADMIN_PIN", "666888")

# Brand Information
STORE_NAME = "ZTS Hub - Zesha Tech Store"
STORE_TAGLINE = "Pusat Top-Up Game, Akun Premium & SMM Otomatis 24 Jam"
STORE_OWNER = "Prince Zesha"
OWNER_WHATSAPP = "6282183872081"

# Provider Modes: 'sandbox' (simulasi otomatis) atau 'live' (tembak API nyata)
PROVIDER_MODE = os.environ.get("PROVIDER_MODE", "sandbox")

# Digiflazz Credentials (Top-Up Game H2H)
DIGIFLAZZ_USERNAME = os.environ.get("DIGIFLAZZ_USERNAME", "zesha_official")
DIGIFLAZZ_API_KEY = os.environ.get("DIGIFLAZZ_API_KEY", "dev-digiflazz-key")

# Payment Gateway Credentials (Tripay / Pakasir / QRIS)
PAYMENT_GATEWAY = os.environ.get("PAYMENT_GATEWAY", "simulator")
TRIPAY_API_KEY = os.environ.get("TRIPAY_API_KEY", "mock-tripay-key")
TRIPAY_PRIVATE_KEY = os.environ.get("TRIPAY_PRIVATE_KEY", "mock-private-key")
TRIPAY_MERCHANT_CODE = os.environ.get("TRIPAY_MERCHANT_CODE", "T12345")
