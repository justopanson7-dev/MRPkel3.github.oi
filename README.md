# TempoWorks — Sistem ERP Produksi Jam Dinding

Aplikasi internal untuk mengelola persediaan, produksi, penjualan, pembelian, keuangan, dan perhitungan kebutuhan material pabrik jam dinding.

## Fitur

- Data bahan baku mencakup stok, minimum, harga, pemasok, dan gudang; produk mencakup ukuran, stok, minimum, harga jual, dan BOM.
- Status persediaan **Di bawah minimum**, **Menipis**, atau **Aman**, kapasitas produksi dari ketersediaan bahan, serta HPP bahan ditambah upah rakit Rp20.000 per unit.
- Perintah produksi: **Direncanakan** tidak mengubah stok; mulai produksi memeriksa dan mengurangi seluruh kebutuhan bahan; selesai produksi menambah stok produk jadi.
- Pesanan penjualan menyimpan harga jual dan HPP pada saat dibuat. Pengiriman mengurangi stok produk jadi; pembayaran mencatat kas masuk.
- PO menyimpan harga dan pemasok saat dibuat. Penerimaan PO menambah stok bahan dan mencatat kas keluar; barang datang tidak bisa dicatat sebagai transaksi stok langsung.
- Riwayat stok dan transaksi kas tersimpan dengan nomor dokumen, waktu, dan pengguna.
- Ringkasan keuangan untuk omzet, piutang, komitmen PO, laba kotor, dan saldo kas.
- Hak akses berbasis peran: Admin, Manajer, Staf Gudang, Kepala Produksi, Sales, dan Keuangan.
- Laporan MRP menghitung kebutuhan material dari perintah berstatus **Direncanakan** atau **Dirilis**, lalu membandingkannya dengan stok.
- Histori volume perusahaan dan pesaing per periode, diimpor dari sheet `DATA AWAL`.
- Komponen dan jumlah BOM per produk, diimpor dari sheet `LUAS LANTAI PABRIK`.

> Workbook tidak berisi stok gudang aktual atau tanggal kalender untuk tiap periode. Stok awal komponen diset 0 agar tidak mengarang jumlah. Lakukan stok opname melalui menu **Gudang & bahan** sebelum memakai laporan MRP untuk keputusan produksi. Penerimaan barang dilakukan melalui PO agar perubahan stok dan kas tercatat bersama.
>
> Harga bahan perlu diisi pada data bahan, sedangkan harga jual produk diisi pada katalog produk. HPP dan harga pada pesanan penjualan dikunci saat pesanan dibuat. Koreksi kas dilakukan dengan transaksi baru, bukan mengubah/menghapus transaksi historis.

## Menjalankan secara lokal

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Buka `http://127.0.0.1:8000/` dan masuk menggunakan akun superuser yang dibuat. Superuser memperoleh hak Admin; Admin dapat membuat akun dan menetapkan peran melalui menu **Pengguna**. Django Admin tersedia di `/admin/` untuk administrasi, sedangkan transaksi operasional dilakukan melalui halaman aplikasi.

## Impor workbook perusahaan

Impor histori volume 36 periode, satu produk jam, sembilan bahan, dan komponen BOM:

```powershell
python manage.py import_clock_workbook "D:\ptlf\Data Jam Dinding PTLF(new).xlsx"
```

Perintah ini aman dijalankan ulang: histori periode diperbarui, sementara produk, bahan, dan komponen BOM yang sudah ada tidak digandakan atau ditimpa. Lihat grafik dan tabel melalui menu **Data historis**; masukkan saldo awal melalui stok opname. Periode disimpan sebagai angka berurutan karena tanggal kalender tidak tersedia di workbook.

## Alur transaksi

1. Perbarui data harga bahan, pemasok, gudang, harga jual produk, dan BOM.
2. Buat PO dari bahan yang diperlukan, lalu terima PO untuk menambah stok dan mencatat kas keluar.
3. Buat perintah produksi. Mulai hanya berhasil jika seluruh bahan cukup; tandai selesai untuk menambah stok produk jadi.
4. Buat pesanan penjualan, kirim saat stok produk mencukupi, lalu tandai dibayar untuk mencatat kas masuk dan mengurangi piutang.
5. Gunakan menu **Keuangan** untuk melihat ringkasan serta mencatat transaksi kas non-PO/non-penjualan yang berwenang.

Nomor dokumen WO, SO, dan PO menggunakan format `TIPE-YYMM-001` dan urutannya tidak digunakan ulang.

## Pengujian

```powershell
python manage.py test
python manage.py check
```

SQLite digunakan untuk pengembangan awal. Sebelum deployment, atur `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false`, dan `DJANGO_ALLOWED_HOSTS`; gunakan basis data produksi serta HTTPS.

## Deploy percobaan ke Render

Proyek menyediakan Blueprint di [render.yaml](./render.yaml). Simpan perubahan ke repository GitHub, hubungkan repository tersebut ke Render, lalu buat layanan melalui **New > Blueprint**. Blueprint memasang dependensi, mengumpulkan static files, menjalankan migrasi, dan memulai Gunicorn. Render membuat `DJANGO_SECRET_KEY` secara otomatis; hostname `onrender.com` dan origin HTTPS-nya dibaca dari environment Render.

Blueprint memakai paket Free dan SQLite hanya untuk demo. Penyimpanan lokal layanan Free bersifat sementara; database dan seluruh transaksi dapat hilang saat layanan di-deploy ulang, restart, atau dihentikan. Jangan masukkan data operasional atau data sensitif. Untuk penggunaan nyata, gunakan PostgreSQL terkelola (disarankan) atau paket Render ber-disk persisten dan atur `SQLITE_PATH` ke direktori mount disk.

Setelah deploy berhasil, buat akun admin dari **Shell** pada layanan Render:

```sh
python manage.py createsuperuser
```
