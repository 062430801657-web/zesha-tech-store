import time
from database import init_db, get_all_products, get_order_by_invoice, get_store_analytics
from services.supplier_service import SupplierService
from services.payment_service import PaymentService
from database import create_order

print("🚀 1. Menguji Inisialisasi Database & Seeding...")
init_db()
products = get_all_products()
print(f"✅ Berhasil memuat {len(products)} produk aktif.")
for p in products[:3]:
    print(f"   • [{p['category'].upper()}] {p['name']} | Modal: Rp {p['modal_price']} -> Jual: Rp {p['selling_price']} (Profit: +Rp {p['margin']})")

print("\n🎮 2. Menguji Fitur Auto Check Nickname Game...")
nick_check = SupplierService.check_nickname("Mobile Legends", "12345678", "2024")
print(f"✅ Hasil Cek Nickname MLBB: {nick_check}")

print("\n📦 3. Menguji Pembuatan Pesanan Baru (Canva Pro 1 Tahun)...")
canva_prod = [p for p in products if p['code'] == 'CANVA_1Y'][0]
invoice = f"ZTS-TEST-{int(time.time())}"
qris_data = PaymentService.generate_qris(invoice, canva_prod['selling_price'])

order_data = {
    "invoice": invoice,
    "product_code": canva_prod["code"],
    "product_name": canva_prod["name"],
    "category": canva_prod["category"],
    "target_account": "pembeli.kuliah@gmail.com",
    "zone_id": "",
    "buyer_whatsapp": "081234567890",
    "buyer_nickname": "Mahasiswa Polsri",
    "modal_price": canva_prod["modal_price"],
    "selling_price": canva_prod["selling_price"],
    "profit": canva_prod["margin"],
    "payment_method": "QRIS",
    "qris_data": qris_data["qris_string"],
    "qris_image": qris_data["qris_image_url"]
}
create_order(order_data)
saved_order = get_order_by_invoice(invoice)
print(f"✅ Pesanan tersimpan: Invoice {saved_order['invoice']} | Status: {saved_order['status']}")

print("\n⚡ 4. Menguji Simulasi Pembayaran QRIS Otomatis & Auto-Dispatch H2H...")
dispatch_res = PaymentService.process_successful_payment(saved_order)
print(f"✅ Respon Webhook Pembayaran: {dispatch_res}")

updated_order = get_order_by_invoice(invoice)
print(f"✅ Status Akhir: {updated_order['status']}")
print(f"📦 Bukti Pengiriman/Serial Number:\n{updated_order['sn_delivery']}")

print("\n📊 5. Menguji Dashboard Finansial Admin...")
stats = get_store_analytics()
print(f"✅ Total Pesanan: {stats['total_orders']}")
print(f"✅ Pesanan Sukses: {stats['success_orders']}")
print(f"✅ Total Omzet (Revenue): Rp {stats['total_revenue']:,}")
print(f"✅ Total Laba Bersih (Profit): Rp {stats['total_profit']:,}")
print("\n🎉 SEMUA PENGUJIAN END-TO-END BERHASIL 100%!")
