import os
import random
import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional

from config import STORE_NAME, STORE_TAGLINE, STORE_OWNER, OWNER_WHATSAPP, PORT, HOST
from database import init_db, get_all_products, get_product_by_code, create_order, get_order_by_invoice, get_store_analytics
from services.supplier_service import SupplierService
from services.payment_service import PaymentService

# Inisialisasi Database
init_db()

app = FastAPI(title=STORE_NAME, description=STORE_TAGLINE, version="1.0.0")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Health check wajib untuk Koyeb Deployment
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
    return templates.TemplateResponse(
        request=request,
        name="invoice.html",
        context={
            "store_name": STORE_NAME,
            "store_owner": STORE_OWNER,
            "owner_whatsapp": OWNER_WHATSAPP,
            "order": order
        }
    )

# 3. Halaman Dashboard Admin
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
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

class CheckIDRequest(BaseModel):
    brand: str
    user_id: str
    zone_id: Optional[str] = None

@app.post("/api/order/check-id")
async def api_check_id(req: CheckIDRequest):
    result = SupplierService.check_nickname(req.brand, req.user_id, req.zone_id)
    return result

class CreateOrderRequest(BaseModel):
    product_code: str
    target_account: str
    zone_id: Optional[str] = ""
    buyer_whatsapp: str

@app.post("/api/order/create")
async def api_create_order(req: CreateOrderRequest):
    prod = get_product_by_code(req.product_code)
    if not prod:
        return {"success": False, "message": "Produk tidak ditemukan atau non-aktif."}

    # Generate Invoice Unik: ZTS-YYMMDD-RAND
    invoice = f"ZTS-{time.strftime('%y%m%d')}-{random.randint(1000, 9999)}"

    # Generate QRIS Dinamis
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

@app.get("/api/order/{invoice}")
async def api_get_order_status(invoice: str):
    order = get_order_by_invoice(invoice)
    if not order:
        return {"status": "NOT_FOUND"}
    return {
        "invoice": order["invoice"],
        "status": order["status"],
        "sn_delivery": order["sn_delivery"]
    }

class WebhookPaymentRequest(BaseModel):
    invoice: str
    status: str
    channel: Optional[str] = "QRIS"

@app.post("/api/webhook/payment")
async def api_webhook_payment(req: WebhookPaymentRequest):
    order = get_order_by_invoice(req.invoice)
    if not order:
        return {"status": "FAILED", "message": "Invoice tidak ditemukan."}

    if order["status"] == "SUCCESS":
        return {"status": "SUCCESS", "message": "Order sudah sukses sebelumnya."}

    # Proses pengiriman produk otomatis H2H
    dispatch_res = PaymentService.process_successful_payment(order)
    return dispatch_res

@app.get("/api/admin/stats")
async def api_admin_stats():
    return get_store_analytics()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True)
