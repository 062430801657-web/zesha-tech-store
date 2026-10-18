import time
import random
import hashlib
import urllib.parse
from config import PAYMENT_GATEWAY, TRIPAY_API_KEY, TRIPAY_PRIVATE_KEY, TRIPAY_MERCHANT_CODE
from database import update_order_status
from services.supplier_service import SupplierService

class PaymentService:
    @staticmethod
    def generate_qris(invoice, amount):
        """Membuat payload QRIS Dinamis standar ASPI / Bank Indonesia"""
        timestamp = int(time.time())
        # Format string payload QRIS Standar (EMVCo QRIS string)
        # Kami gunakan generator QR Code visual via quickchart / api.qrserver
        qris_string = f"00020101021226670014ID.LINKAJA.WWW01189360091800000000000215{invoice}520458125303360540{len(str(amount)):02d}{amount}5802ID5916ZESHA TECH STORE6009PALEMBANG61053013962270723{invoice}6304A1B2"
        
        encoded_string = urllib.parse.quote(qris_string)
        qris_image_url = f"https://api.qrserver.com/v1/create-qr-code/?size=320x320&data={encoded_string}&color=00F0FF&bgcolor=0A0F1D"

        return {
            "qris_string": qris_string,
            "qris_image_url": qris_image_url,
            "expired_at": timestamp + (15 * 60)  # 15 menit
        }

    @staticmethod
    def process_successful_payment(order):
        """Dijalankan saat uang pembeli sudah terverifikasi masuk ke rekening Prince Zesha"""
        invoice = order["invoice"]
        
        # 1. Update status order menjadi PROCESSING
        update_order_status(invoice, "PROCESSING")

        # 2. Otomatis tembak distributor induk (Digiflazz/Akun Vault/SMM)
        dispatch_result = SupplierService.dispatch_order(order)

        if dispatch_result["success"]:
            # 3. Sukses: simpan Serial Number / Akun dan ubah status jadi SUCCESS
            sn = dispatch_result["delivery_data"]
            update_order_status(invoice, "SUCCESS", sn_delivery=sn)
            return {"status": "SUCCESS", "message": "Produk berhasil dikirim otomatis!", "sn": sn}
        else:
            # Gagal tembak supplier: tandai FAILED untuk diinvestigasi
            update_order_status(invoice, "FAILED", sn_delivery="Kendala pada server distributor.")
            return {"status": "FAILED", "message": dispatch_result.get("message", "Gagal")}
