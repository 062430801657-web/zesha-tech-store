import sqlite3
import json
import time
from datetime import datetime
import urllib.request
from config import DB_PATH, GIST_ID, GH_STORAGE_TOKEN

def _get_cloud_headers():
    token = GH_STORAGE_TOKEN
    if not token:
        # Fallback lokal jika dijalankan di mesin Linux dev
        try:
            import subprocess
            token = subprocess.check_output(['gh', 'auth', 'token'], timeout=2).decode().strip()
        except Exception:
            token = ""
    return {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'ZTS-Hub-Cloud-DB'
    }

def _fetch_all_cloud_orders():
    if not GIST_ID:
        return {}
    try:
        req = urllib.request.Request(
            f'https://api.github.com/gists/{GIST_ID}',
            headers=_get_cloud_headers()
        )
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            data = json.loads(resp.read().decode())
            return json.loads(data['files']['orders.json']['content'])
    except Exception:
        return {}

def _save_order_to_cloud(order_dict):
    if not GIST_ID:
        return False
    try:
        orders = _fetch_all_cloud_orders()
        orders[order_dict['invoice']] = order_dict
        req = urllib.request.Request(
            f'https://api.github.com/gists/{GIST_ID}',
            headers=_get_cloud_headers(),
            data=json.dumps({'files': {'orders.json': {'content': json.dumps(orders, indent=2)}}}).encode(),
            method='PATCH'
        )
        with urllib.request.urlopen(req, timeout=3.5) as resp:
            return True
    except Exception:
        return False

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db()
    cursor = conn.cursor()

    # Tabel Produk
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,          -- 'game', 'premium', 'smm'
        code TEXT UNIQUE NOT NULL,        -- 'MLBB_WDP', 'CANVA_1Y', dll
        brand TEXT NOT NULL,             -- 'Mobile Legends', 'Canva', 'Netflix'
        name TEXT NOT NULL,
        icon TEXT,
        modal_price INTEGER NOT NULL,    -- Harga modal dari supplier
        selling_price INTEGER NOT NULL,  -- Harga jual ke pembeli
        margin INTEGER NOT NULL,         -- Keuntungan bersih
        description TEXT,
        input_type TEXT DEFAULT 'id',    -- 'game_id_zone', 'email', 'social_username'
        is_active INTEGER DEFAULT 1
    );
    """)

    # Tabel Pesanan
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice TEXT UNIQUE NOT NULL,
        product_code TEXT NOT NULL,
        product_name TEXT NOT NULL,
        category TEXT NOT NULL,
        target_account TEXT NOT NULL,    -- ID Game, Email pembeli, username IG
        zone_id TEXT,                    -- Zone ID untuk game tertentu
        buyer_whatsapp TEXT NOT NULL,
        buyer_nickname TEXT,             -- Hasil auto check nickname
        modal_price INTEGER NOT NULL,
        selling_price INTEGER NOT NULL,
        profit INTEGER NOT NULL,
        payment_method TEXT DEFAULT 'QRIS',
        qris_data TEXT,
        qris_image TEXT,
        status TEXT DEFAULT 'UNPAID',    -- UNPAID, PAID, PROCESSING, SUCCESS, FAILED
        sn_delivery TEXT,                -- SN transaksi atau Akun:Password
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Tabel Brankas Stok Instan Akun Premium
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stock_vault (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_code TEXT NOT NULL,
        credential_data TEXT NOT NULL,   -- 'Email:Pass | Profil 2 (PIN 1234)'
        is_used INTEGER DEFAULT 0,
        used_for_invoice TEXT,
        created_at TEXT NOT NULL
    );
    """)

    conn.commit()

    # Seed Data Produk jika masih kosong
    cursor.execute("SELECT COUNT(*) FROM products;")
    if cursor.fetchone()[0] == 0:
        seed_default_products(cursor)
        conn.commit()

    conn.close()

def seed_default_products(cursor):
    default_products = [
        # 1. KATEGORI TOP-UP GAME H2H
        ("game", "MLBB_WDP", "Mobile Legends", "Weekly Diamond Pass (WDP)", "gamepad", 26500, 31500, 5000, "1x Weekly Diamond Pass Resmi Moonton. Hemat 400% diamond + item harian.", "game_id_zone"),
        ("game", "MLBB_86", "Mobile Legends", "86 Diamonds (78 + 8 Bonus)", "gamepad", 19200, 23500, 4300, "Top-up diamond Mobile Legends kilat 3-5 detik masuk.", "game_id_zone"),
        ("game", "MLBB_172", "Mobile Legends", "172 Diamonds (156 + 16 Bonus)", "gamepad", 38400, 46000, 7600, "Top-up diamond Mobile Legends kilat 3-5 detik masuk.", "game_id_zone"),
        ("game", "FF_140", "Free Fire", "140 Diamonds Free Fire", "fire", 18500, 22000, 3500, "Top-up diamond Free Fire langsung ke User ID.", "id"),
        ("game", "GI_BLESSING", "Genshin Impact", "Blessing of the Welkin Moon", "sparkles", 68000, 79000, 11000, "300 Genesis Crystals + 90 Primogems harian selama 30 hari.", "game_id_zone"),

        # 2. KATEGORI APLIKASI PREMIUM
        ("premium", "CANVA_1Y", "Canva", "Canva Pro - Durasi 1 Tahun (Invite Email)", "palette", 1000, 20000, 19000, "Upgrade email pribadi Anda jadi Canva Pro 1 Tahun penuh. Bebas fitur desainer, font, dan template premium.", "email"),
        ("premium", "NETFLIX_1P1U", "Netflix", "Netflix Premium 4K UHD - 1 Bulan (1P1U)", "tv", 26000, 39000, 13000, "1 Profil Khusus 1 Pengguna dengan PIN pribadi. Kualitas Ultra HD 4K, anti antre layar.", "email"),
        ("premium", "YOUTUBE_1M", "YouTube", "YouTube Premium - 1 Bulan (Family Plan Invite)", "video", 8000, 20000, 12000, "Bebas iklan, download video offline, background playback & YouTube Music resmi.", "email"),
        ("premium", "SPOTIFY_1M", "Spotify", "Spotify Premium Individual - 1 Bulan", "music", 11000, 24000, 13000, "Dengarkan musik tanpa jeda iklan, skip lagu bebas tak terbatas, download lagu offline.", "email"),
        ("premium", "CAPCUT_1M", "CapCut", "CapCut Pro Video Editor - 1 Bulan", "scissors", 8000, 25000, 17000, "Akses seluruh filter pro, subtitle otomatis AI, dan hilangkan watermark selamanya.", "email"),

        # 3. KATEGORI SMM PANEL
        ("smm", "IG_FOLL_1K", "Instagram", "1.000 Followers Instagram (HQ Refill)", "instagram", 8500, 25000, 16500, "Kualitas akun High Quality, bergaransi isi ulang (refill 30 hari). Masukkan username tanpa @.", "social_username"),
        ("smm", "TT_VIEWS_10K", "TikTok", "10.000 Views Video TikTok (Instant Viral)", "trending-up", 1500, 10000, 8500, "Mendongkrak algoritma FYP TikTok seketika. Proses otomatis dalam hitungan menit.", "social_username"),
        ("smm", "TT_FOLL_1K", "TikTok", "1.000 Followers TikTok Aktif", "users", 24000, 50000, 26000, "Membuka syarat live streaming TikTok dan fitur keranjang kuning (TikTok Shop).", "social_username")
    ]

    for p in default_products:
        cursor.execute("""
        INSERT INTO products (category, code, brand, name, icon, modal_price, selling_price, margin, description, input_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, p)

def get_all_products(category=None):
    conn = get_db()
    cursor = conn.cursor()
    if category:
        cursor.execute("SELECT * FROM products WHERE category = ? AND is_active = 1 ORDER BY id ASC;", (category,))
    else:
        cursor.execute("SELECT * FROM products WHERE is_active = 1 ORDER BY category ASC, id ASC;")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

def get_product_by_code(code):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM products WHERE code = ? AND is_active = 1;", (code,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def create_order(order_data):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute("""
    INSERT INTO orders (
        invoice, product_code, product_name, category, target_account, zone_id,
        buyer_whatsapp, buyer_nickname, modal_price, selling_price, profit,
        payment_method, qris_data, qris_image, status, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, (
        order_data["invoice"],
        order_data["product_code"],
        order_data["product_name"],
        order_data["category"],
        order_data["target_account"],
        order_data.get("zone_id", ""),
        order_data["buyer_whatsapp"],
        order_data.get("buyer_nickname", "Player/Member"),
        order_data["modal_price"],
        order_data["selling_price"],
        order_data["profit"],
        order_data.get("payment_method", "QRIS"),
        order_data.get("qris_data", ""),
        order_data.get("qris_image", ""),
        "UNPAID",
        now,
        now
    ))
    conn.commit()
    conn.close()
    # Sinkronisasi ke Cloud Storage Gist
    try:
        _save_order_to_cloud(dict(order_data))
    except Exception:
        pass

def get_order_by_invoice(invoice):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders WHERE invoice = ?;", (invoice,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)

    # Jika tidak ada di SQLite lokal (misal: cold start serverless baru), cari di cloud storage
    cloud_orders = _fetch_all_cloud_orders()
    if invoice in cloud_orders:
        cloud_data = cloud_orders[invoice]
        # Simpan ke cache SQLite lokal
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO orders (
                invoice, product_code, product_name, category, target_account, zone_id,
                buyer_whatsapp, buyer_nickname, modal_price, selling_price, profit,
                payment_method, qris_data, qris_image, status, sn_delivery, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                cloud_data["invoice"],
                cloud_data.get("product_code", ""),
                cloud_data.get("product_name", ""),
                cloud_data.get("category", ""),
                cloud_data.get("target_account", ""),
                cloud_data.get("zone_id", ""),
                cloud_data.get("buyer_whatsapp", ""),
                cloud_data.get("buyer_nickname", ""),
                cloud_data.get("modal_price", 0),
                cloud_data.get("selling_price", 0),
                cloud_data.get("profit", 0),
                cloud_data.get("payment_method", "QRIS"),
                cloud_data.get("qris_data", ""),
                cloud_data.get("qris_image", ""),
                cloud_data.get("status", "UNPAID"),
                cloud_data.get("sn_delivery", None),
                cloud_data.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                cloud_data.get("updated_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            ))
            conn.commit()
            conn.close()
        except Exception:
            pass
        return cloud_data

    return None

def update_order_status(invoice, status, sn_delivery=None):
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if sn_delivery:
        cursor.execute("""
        UPDATE orders SET status = ?, sn_delivery = ?, updated_at = ? WHERE invoice = ?;
        """, (status, sn_delivery, now, invoice))
    else:
        cursor.execute("""
        UPDATE orders SET status = ?, updated_at = ? WHERE invoice = ?;
        """, (status, now, invoice))
    conn.commit()
    conn.close()

    # Perbarui data di cloud storage
    try:
        cloud_orders = _fetch_all_cloud_orders()
        if invoice in cloud_orders:
            cloud_orders[invoice]["status"] = status
            if sn_delivery:
                cloud_orders[invoice]["sn_delivery"] = sn_delivery
            cloud_orders[invoice]["updated_at"] = now
            _save_order_to_cloud(cloud_orders[invoice])
    except Exception:
        pass

def get_store_analytics():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM orders;")
    total_orders = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*), COALESCE(SUM(selling_price), 0), COALESCE(SUM(profit), 0) FROM orders WHERE status = 'SUCCESS';")
    success_row = cursor.fetchone()
    success_count = success_row[0]
    total_revenue = success_row[1]
    total_profit = success_row[2]

    cursor.execute("SELECT * FROM orders ORDER BY id DESC LIMIT 15;")
    recent_orders = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return {
        "total_orders": total_orders,
        "success_orders": success_count,
        "total_revenue": total_revenue,
        "total_profit": total_profit,
        "recent_orders": recent_orders
    }
