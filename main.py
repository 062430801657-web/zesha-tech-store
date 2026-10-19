import os
import re
import json
import time
import random
import hmac
import hashlib
from collections import defaultdict
from fastapi import FastAPI, Request, HTTPException, Response, Depends, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator
from typing import Optional

from config import STORE_NAME, STORE_TAGLINE, STORE_OWNER, OWNER_WHATSAPP, PORT, HOST, ADMIN_PIN, SECRET_KEY
from database import init_db, get_all_products, get_product_by_code, create_order, get_order_by_invoice, get_store_analytics, get_db
from services.supplier_service import SupplierService
from services.payment_service import PaymentService

# Inisialisasi Database
init_db()

app = FastAPI(title=STORE_NAME, description=STORE_TAGLINE, version="1.1.0")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# ─── MIDDLEWARE: SECURITY HEADERS ───
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# ─── IN-MEMORY RATE LIMITER (ANTI-DOS SPAM ORDER) ───
RATE_LIMIT_BUCKET = defaultdict(list)

def check_rate_limit(client_ip: str, limit: int = 15, window: int = 60):
    now = time.time()
    # Bersihkan timestamp usang
    RATE_LIMIT_BUCKET[client_ip] = [t for t in RATE_LIMIT_BUCKET[client_ip] if now - t < window]
    if len(RATE_LIMIT_BUCKET[client_ip]) >= limit:
        return False
    RATE_LIMIT_BUCKET[client_ip].append(now)
    return True

# ─── AUTH HELPER UNTUK ADMIN ───
def is_admin_authenticated(request: Request) -> bool:
    token = request.cookies.get("zts_admin_session")
    if not token:
        return False
    expected_token = hmac.new(SECRET_KEY.encode(), f"admin-{ADMIN_PIN}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(token, expected_token)

# Health check wajib untuk Deployment
@app.get("/health")
def health_check():
    return {"status": "ok", "service": "ZTS Hub Storefront", "timestamp": time.time()}

# 1. Halaman Depan Toko
@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    products = get_all_products()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "store_name": STORE_NAME,
            "store_owner": STORE_OWNER,
            "owner_whatsapp": OWNER_WHATSAPP,
            "products": products
        }
    )

# 2. Halaman Invoice & QRIS
@app.get("/order/{invoice}", response_class=HTMLResponse)
async def invoice_page(request: Request, invoice: str):
    order = get_order_by_invoice(invoice)
    if not order:
        raise HTTPException(status_code=404, detail="Invoice tidak ditemukan.")
    # Siapkan signature resmi untuk simulasi pembayaran invoice ini
    test_signature = PaymentService.generate_signature(invoice)
    return templates.TemplateResponse(
        request=request,
        name="invoice.html",
        context={
            "store_name": STORE_NAME,
            "store_owner": STORE_OWNER,
            "owner_whatsapp": OWNER_WHATSAPP,
            "order": order,
            "test_signature": test_signature
        }
    )

# 3. Halaman Dashboard Admin (Terproteksi PIN)
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    if not is_admin_authenticated(request):
        return templates.TemplateResponse(
            request=request,
            name="admin_login.html",
            context={
                "store_name": STORE_NAME,
                "store_owner": STORE_OWNER
            }
        )
    stats = get_store_analytics()
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={
            "store_name": STORE_NAME,
            "store_owner": STORE_OWNER,
            "stats": stats
        }
    )

# ──────────────── API ENDPOINTS ────────────────

class AdminAuthRequest(BaseModel):
    pin: str

@app.post("/api/admin/auth")
async def api_admin_auth(req: AdminAuthRequest, response: Response):
    if req.pin == ADMIN_PIN:
        token = hmac.new(SECRET_KEY.encode(), f"admin-{ADMIN_PIN}".encode(), hashlib.sha256).hexdigest()
        response.set_cookie(
            key="zts_admin_session",
            value=token,
            httponly=True,
            max_age=86400 * 7,  # 7 Hari
            samesite="lax"
        )
        return {"success": True, "message": "Autentikasi PIN Berhasil"}
    return JSONResponse(status_code=401, content={"success": False, "message": "PIN Admin Salah"})

@app.get("/api/admin/logout")
async def api_admin_logout(response: Response):
    response.delete_cookie("zts_admin_session")
    return RedirectResponse(url="/admin")

class CheckIDRequest(BaseModel):
    brand: str
    user_id: str
    zone_id: Optional[str] = None

@app.post("/api/order/check-id")
async def api_check_id(req: CheckIDRequest):
    # Bersihkan input dari tag berbahaya
    clean_user = re.sub(r"[^\w\-\.]", "", req.user_id)
    clean_zone = re.sub(r"[^\w\-\.]", "", req.zone_id) if req.zone_id else ""
    result = SupplierService.check_nickname(req.brand, clean_user, clean_zone)
    return result

class CreateOrderRequest(BaseModel):
    product_code: str
    target_account: str
    zone_id: Optional[str] = ""
    buyer_whatsapp: str

    @field_validator("buyer_whatsapp")
    def validate_phone(cls, v):
        clean = re.sub(r"[\s\-\+]", "", v)
        if not re.match(r"^(08|628)[0-9]{8,13}$", clean):
            raise ValueError("Nomor WhatsApp tidak valid. Gunakan format 08xxx atau 628xxx (10-14 digit).")
        return clean

    @field_validator("target_account")
    def sanitize_target(cls, v):
        clean = re.sub(r"[<>'\"/\\;]", "", v).strip()
        if len(clean) < 2 or len(clean) > 80:
            raise ValueError("Target akun tidak valid (minimal 2 karakter, maksimal 80 karakter).")
        return clean

@app.post("/api/order/create")
async def api_create_order(req: CreateOrderRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(client_ip):
        return JSONResponse(
            status_code=429,
            content={"success": False, "message": "Terlalu banyak permintaan order. Silakan tunggu 1 menit."}
        )

    prod = get_product_by_code(req.product_code)
    if not prod:
        return {"success": False, "message": "Produk tidak ditemukan atau non-aktif."}

    # Generate Invoice Unik: ZTS-YYMMDD-RAND
    invoice = f"ZTS-{time.strftime('%y%m%d')}-{random.randint(1000, 9999)}"

    # Generate QRIS Dinamis & HMAC Signature
    qris_info = PaymentService.generate_qris(invoice, prod["selling_price"])

    order_payload = {
        "invoice": invoice,
        "product_code": prod["code"],
        "product_name": prod["name"],
        "category": prod["category"],
        "target_account": req.target_account,
        "zone_id": req.zone_id,
        "buyer_whatsapp": req.buyer_whatsapp,
        "buyer_nickname": "Player/Customer",
        "modal_price": prod["modal_price"],
        "selling_price": prod["selling_price"],
        "profit": prod["margin"],
        "payment_method": "QRIS",
        "qris_data": qris_info["qris_string"],
        "qris_image": qris_info["qris_image_url"]
    }

    create_order(order_payload)

    return {
        "success": True,
        "invoice": invoice,
        "redirect_url": f"/order/{invoice}"
    }

# ─── FITUR CEK PESANAN / ORDER LOOKUP (Wajib ditaruh sebelum path param {invoice}) ───
@app.get("/api/order/lookup")
async def api_order_lookup(query: str):
    clean_q = query.strip()
    if not clean_q:
        return {"orders": []}
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT invoice, product_name, selling_price, status, created_at, sn_delivery
    FROM orders 
    WHERE invoice = ? OR buyer_whatsapp LIKE ?
    ORDER BY id DESC LIMIT 5;
    """, (clean_q, f"%{clean_q}%"))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"orders": rows}

@app.get("/api/order/{invoice}")
async def api_get_order_status(invoice: str):
    clean_inv = re.sub(r"[^\w\-]", "", invoice)
    order = get_order_by_invoice(clean_inv)
    if not order:
        return {"status": "NOT_FOUND"}
    return {
        "invoice": order["invoice"],
        "status": order["status"],
        "sn_delivery": order["sn_delivery"]
    }

# ─── WEBHOOK PEMBAYARAN TERLINDUNGI HMAC SIGNATURE ───
class WebhookPaymentRequest(BaseModel):
    invoice: str
    status: str
    channel: Optional[str] = "QRIS"
    signature: Optional[str] = None

@app.post("/api/webhook/payment")
async def api_webhook_payment(req: WebhookPaymentRequest, request: Request):
    clean_inv = re.sub(r"[^\w\-]", "", req.invoice)
    order = get_order_by_invoice(clean_inv)
    if not order:
        return {"status": "FAILED", "message": "Invoice tidak ditemukan."}

    if order["status"] == "SUCCESS":
        return {"status": "SUCCESS", "message": "Order sudah sukses sebelumnya."}

    # Verifikasi Keamanan: Cek HMAC Signature dari Header atau Body Payload
    incoming_sign = request.headers.get("X-Webhook-Signature") or req.signature
    if not PaymentService.verify_signature(clean_inv, incoming_sign):
        return JSONResponse(
            status_code=403,
            content={"status": "FORBIDDEN", "message": "Signature verifikasi webhook tidak valid atau dipalsukan."}
        )

    # Proses pengiriman produk otomatis H2H
    dispatch_res = PaymentService.process_successful_payment(order)
    return dispatch_res

# ─── AUTO-SETTLEMENT TRIPAY & PAKASIR WEBHOOK CALLBACK ───
@app.post("/api/webhook/tripay")
async def api_webhook_tripay(request: Request):
    try:
        body = await request.body()
        data = json.loads(body.decode())
        incoming_sign = request.headers.get("X-Callback-Signature", "")
        
        # Verifikasi signature Tripay: HMAC-SHA256(body, private_key)
        from config import TRIPAY_PRIVATE_KEY
        if TRIPAY_PRIVATE_KEY and TRIPAY_PRIVATE_KEY != "mock-private-key":
            expected = hmac.new(TRIPAY_PRIVATE_KEY.encode(), body, hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, incoming_sign):
                return JSONResponse(status_code=403, content={"success": False, "message": "Invalid Tripay Signature"})

        merchant_ref = data.get("merchant_ref")
        status = data.get("status", "").upper()
        if merchant_ref and status == "PAID":
            order = get_order_by_invoice(merchant_ref)
            if order and order["status"] != "SUCCESS":
                PaymentService.process_successful_payment(order)
                return {"success": True, "message": "Tripay payment settled successfully"}

        return {"success": True}
    except Exception as e:
        return JSONResponse(status_code=400, content={"success": False, "error": str(e)})

@app.post("/api/admin/order/{invoice}/approve")
async def api_admin_approve_order(invoice: str, request: Request):
    """Admin manual override: Konfirmasi pembayaran langsung dari dashboard admin"""
    if not is_admin_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    clean_inv = re.sub(r"[^\w\-]", "", invoice)
    order = get_order_by_invoice(clean_inv)
    if not order:
        return {"status": "FAILED", "message": "Invoice tidak ditemukan."}
    
    dispatch_res = PaymentService.process_successful_payment(order)
    return {"status": "SUCCESS", "message": f"Order {clean_inv} berhasil disetujui & diproses otomatis!", "detail": dispatch_res}

@app.get("/api/admin/stats")
async def api_admin_stats(request: Request):
    if not is_admin_authenticated(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return get_store_analytics()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
