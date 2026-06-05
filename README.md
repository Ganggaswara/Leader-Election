# 🎫 Helpdesk System - Distributed Microservices Architecture

Sebuah sistem *ticketing helpdesk* berbasis arsitektur *microservices* terdistribusi. Sistem ini dirancang dengan skalabilitas tinggi, ketersediaan tinggi (*High Availability*), dan menggunakan sistem pemilihan pemimpin (*Leader Election*) otomatis.

## 🏗️ Arsitektur Sistem

Sistem ini terdiri dari beberapa komponen yang berjalan di dalam *container* Docker:

1. **Load Balancer (Port 5000):** Bertindak sebagai gerbang utama (*Reverse Proxy*) yang mendistribusikan *traffic* dari klien ke beberapa instans `Ticket Service` menggunakan algoritma *Thread-Safe Round-Robin*.
2. **Ticket Service (4 Replicas):** Layanan API Gateway berbasis Flask yang menangani operasi CRUD untuk tiket. Layanan ini menyimpan data langsung ke PostgreSQL dan berkomunikasi dengan `Notification Service` melalui JSON-RPC.
3. **Notification Service (6 Replicas):** Kluster pekerja (*worker nodes*) yang menggunakan **Algoritma Hirschberg-Sinclair** untuk melakukan *Leader Election*. Pemimpin yang terpilih bertugas menerima instruksi penyelesaian tiket (*resolve*) dan meneruskannya ke antrean RabbitMQ, di mana seluruh *node* bertindak sebagai *consumer* untuk memproses notifikasi (simulasi pengiriman email).
4. **PostgreSQL (Port 5432):** Basis data relasional utama untuk menyimpan data aduan pelanggan secara persisten.
5. **RabbitMQ (Port 5672 & 15672):** *Message broker* yang menangani antrean tugas asinkron (*asynchronous task queue*) untuk pengiriman notifikasi penyelesaian tiket.

---

## 🚀 Prasyarat

Pastikan sistem Anda telah terinstal:
- [Docker](https://www.docker.com/get-started/) dan Docker Compose
- Python 3.8+ (opsional, jika ingin menjalankan klien atau *load testing* secara lokal)

---

## 🛠️ Cara Menjalankan Aplikasi

1. **Jalankan seluruh layanan menggunakan Docker Compose:**
   ```bash
   docker compose up -d --build
   ```

2. **Periksa status layanan:**
   ```bash
   docker compose ps
   ```

3. **Lihat log layanan (Opsional):**
   ```bash
   docker compose logs -f
   ```
   *Atau spesifik ke salah satu service:*
   ```bash
   docker compose logs -f notification-1
   ```

---

## 📡 API Endpoints

Akses API melalui Load Balancer di `http://localhost:5000`.

### Manajemen Tiket
| Method | Endpoint | Deskripsi |
| :--- | :--- | :--- |
| `POST` | `/tickets` | Membuat tiket aduan baru. *Body: `customer_name`, `issue_title`, `description`* |
| `GET` | `/tickets` | Mengambil seluruh daftar tiket. |
| `GET` | `/tickets/<id>` | Mengambil detail tiket berdasarkan ID. |
| `PUT` | `/tickets/<id>` | Mengubah data tiket. |
| `DELETE`| `/tickets/<id>` | Menghapus data tiket. |

### Resolusi & Status Sistem
| Method | Endpoint | Deskripsi |
| :--- | :--- | :--- |
| `POST` | `/tickets/<id>/resolve` | Menyelesaikan tiket. Memicu sistem RPC ke kluster notifikasi dan mengantrekan ke RabbitMQ. *Body: `resolution`* |
| `GET` | `/cluster/status` | Melihat status sistem terdistribusi, mengetahui *Leader* yang aktif, dan memonitor *election*. |

---

## 👑 Uji Coba Failover & Leader Election

Sistem ini menerapkan algoritma Hirschberg-Sinclair. Jika *Leader* saat ini mati, kluster akan secara otomatis mengadakan pemilihan untuk menentukan *Leader* baru.

1. **Cek Leader Saat Ini:**
   Buka browser atau gunakan cURL ke `http://localhost:5000/cluster/status` dan perhatikan node mana yang bertindak sebagai `"leader"`.
2. **Matikan Leader:**
   Misal `notification-6` adalah leader, matikan dengan:
   ```bash
   docker compose stop notification-6
   ```
3. **Amati Pemilihan Ulang:**
   Tunggu sekitar 5-6 detik. Node lain akan mendeteksi putusnya *heartbeat* dan memulai pemilihan baru. Cek log:
   ```bash
   docker compose logs -f notification-1
   ```
4. **Hidupkan Kembali Node (Opsional):**
   ```bash
   docker compose start notification-6
   ```
   Node akan bergabung kembali ke kluster sebagai *Follower*.

---

## 📈 Load Testing (Locust)

Sistem ini dilengkapi dengan *script* pengujian beban (`locustfile.py`) yang akan menyimulasikan ratusan hingga ribuan *concurrent users* untuk mengakses API.

1. **Instal Locust:**
   ```bash
   pip install locust
   ```
2. **Jalankan Locust:**
   ```bash
   locust -f locustfile.py
   ```
3. **Mulai Pengujian:**
   Buka browser dan akses **`http://localhost:8089`**. Masukkan jumlah target *users* dan *spawn rate*, lalu arahkan host ke `http://localhost:5000`.

