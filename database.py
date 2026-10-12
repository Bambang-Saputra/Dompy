import calendar
import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import config

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(config.ZONA_WAKTU)
except Exception:
    TZ = timezone(timedelta(hours=7))  # cadangan kalau data zona waktu tidak tersedia

os.makedirs(config.DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(config.DATA_DIR, "dompy.db")

KATEGORI = ["Makanan", "Transportasi", "Belanja", "Hiburan", "Tagihan", "Kesehatan", "Pendidikan", "Lainnya"]
SINONIM_KATEGORI = {
    "makan": "Makanan", "minum": "Makanan", "jajan": "Makanan", "kuliner": "Makanan", "food": "Makanan",
    "transport": "Transportasi", "bensin": "Transportasi", "ojol": "Transportasi", "parkir": "Transportasi",
    "shopping": "Belanja", "groceries": "Belanja",
    "nonton": "Hiburan", "game": "Hiburan", "langganan": "Hiburan",
    "listrik": "Tagihan", "pulsa": "Tagihan", "internet": "Tagihan", "kos": "Tagihan", "sewa": "Tagihan",
    "obat": "Kesehatan", "dokter": "Kesehatan",
    "buku": "Pendidikan", "kursus": "Pendidikan", "kuliah": "Pendidikan",
    "lain": "Lainnya", "lain-lain": "Lainnya",
    "total": "Total", "semua": "Total", "keseluruhan": "Total", "all": "Total",
}
NAMA_HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            amount INTEGER NOT NULL,
            period TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            amount INTEGER NOT NULL,
            description TEXT,
            date TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chat_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)


init_db()


def normalisasi_kategori(nama):
    key = (nama or "").strip().lower()
    if not key:
        return "Lainnya"
    for k in KATEGORI:
        if key == k.lower():
            return k
    return SINONIM_KATEGORI.get(key, nama.strip().title())


def rupiah(x):
    x = int(round(x))
    return ("-" if x < 0 else "") + "Rp" + f"{abs(x):,}".replace(",", ".")


def hari_ini():
    return datetime.now(TZ).date()


def sekarang():
    return datetime.now(TZ).isoformat(timespec="seconds")


def ke_tanggal(teks):
    teks = (teks or "").strip()
    return date.fromisoformat(teks) if teks else hari_ini()


def akhir_bulan(d):
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def tambah_bulan(d, n=1):
    bulan = d.month - 1 + n
    tahun = d.year + bulan // 12
    bulan = bulan % 12 + 1
    return date(tahun, bulan, min(d.day, calendar.monthrange(tahun, bulan)[1]))


def hitung_periode(period, start_date="", end_date=""):
    """Mengubah nama periode menjadi (nama_baku, tanggal_mulai, tanggal_selesai)."""
    p = (period or "").strip().lower()
    today = hari_ini()
    if p in ("harian", "hari", "daily", "hari ini"):
        mulai = ke_tanggal(start_date)
        return "harian", mulai, mulai
    if p in ("mingguan", "minggu", "weekly", "minggu ini"):
        mulai = ke_tanggal(start_date) if start_date else today - timedelta(days=today.weekday())
        return "mingguan", mulai, mulai + timedelta(days=6)
    if p in ("bulanan", "bulan", "monthly", "bulan ini"):
        if start_date:
            mulai = ke_tanggal(start_date)
            return "bulanan", mulai, tambah_bulan(mulai) - timedelta(days=1)
        return "bulanan", today.replace(day=1), akhir_bulan(today)
    if p == "custom":
        if not (start_date and end_date):
            raise ValueError("Periode custom butuh start_date dan end_date (format YYYY-MM-DD).")
        mulai, selesai = ke_tanggal(start_date), ke_tanggal(end_date)
        if selesai < mulai:
            raise ValueError("end_date tidak boleh sebelum start_date.")
        return "custom", mulai, selesai
    raise ValueError(f"Periode '{period}' tidak dikenal. Pilih harian, mingguan, bulanan, atau custom.")


def periode_sebelumnya(mulai, selesai):
    """Rentang dengan panjang sama tepat sebelum periode ini (bulan kalender tetap dihitung per bulan)."""
    if mulai.day == 1 and selesai == akhir_bulan(mulai):
        prev_selesai = mulai - timedelta(days=1)
        return prev_selesai.replace(day=1), prev_selesai
    panjang = (selesai - mulai).days + 1
    return mulai - timedelta(days=panjang), mulai - timedelta(days=1)


def total_pengeluaran(mulai, selesai, kategori=None):
    sql = "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE date BETWEEN ? AND ?"
    args = [mulai.isoformat(), selesai.isoformat()]
    if kategori and kategori != "Total":
        sql += " AND category = ?"
        args.append(kategori)
    with db() as conn:
        return conn.execute(sql, args).fetchone()[0]


def ambil_pengeluaran(mulai, selesai):
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM expenses WHERE date BETWEEN ? AND ? ORDER BY date, id",
            (mulai.isoformat(), selesai.isoformat()),
        ).fetchall()
    return [dict(r) for r in rows]


def budget_aktif(pada=None):
    """Budget yang berlaku pada tanggal tertentu, satu per kategori (yang terbaru dibuat)."""
    pada = (pada or hari_ini()).isoformat()
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM budgets WHERE start_date <= ? AND end_date >= ? ORDER BY created_at DESC, id DESC",
            (pada, pada),
        ).fetchall()
    hasil = {}
    for r in rows:
        hasil.setdefault(r["category"], dict(r))
    return list(hasil.values())


def status_budget(b):
    """Kondisi satu budget: terpakai, sisa, jatah per hari, proyeksi, dan level peringatan."""
    mulai, selesai = date.fromisoformat(b["start_date"]), date.fromisoformat(b["end_date"])
    terpakai = total_pengeluaran(mulai, selesai, b["category"])
    sisa = b["amount"] - terpakai
    persen = terpakai / b["amount"] * 100 if b["amount"] else 0
    today = hari_ini()
    total_hari = (selesai - mulai).days + 1
    hari_berjalan = max(0, min((today - mulai).days + 1, total_hari))
    hari_tersisa = (selesai - max(today, mulai)).days + 1 if today <= selesai else 0
    proyeksi = terpakai / hari_berjalan * total_hari if hari_berjalan else terpakai
    level = "lewat budget" if persen >= 100 else "waspada" if persen >= 75 else "aman"
    return {
        "kategori": b["category"],
        "periode": b["period"],
        "mulai": b["start_date"],
        "selesai": b["end_date"],
        "budget": rupiah(b["amount"]),
        "terpakai": rupiah(terpakai),
        "sisa": rupiah(sisa),
        "persen_terpakai": round(persen, 1),
        "hari_tersisa": hari_tersisa,
        "jatah_per_hari": rupiah(sisa / hari_tersisa) if hari_tersisa and sisa > 0 else rupiah(0),
        "proyeksi_akhir_periode": rupiah(proyeksi),
        "level": level,
    }


def jejak_data():
    """Sidik jari isi tabel budget & transaksi, untuk tahu apakah ada yang berubah."""
    with db() as conn:
        return tuple(conn.execute(
            "SELECT (SELECT COUNT(*) FROM expenses), (SELECT COALESCE(MAX(id), 0) FROM expenses),"
            " (SELECT COUNT(*) FROM budgets), (SELECT COALESCE(MAX(id), 0) FROM budgets)").fetchone())


def simpan_chat(role, content):
    with db() as conn:
        conn.execute("INSERT INTO chat_log (role, content, created_at) VALUES (?, ?, ?)", (role, content, sekarang()))


def muat_chat(limit=config.RIWAYAT_CHAT_DIMUAT):
    with db() as conn:
        rows = conn.execute("SELECT role, content FROM chat_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    rows = [dict(r) for r in reversed(rows)]
    while rows and rows[0]["role"] != "user":  # riwayat Gemini harus diawali pesan user
        rows.pop(0)
    return rows


def hapus_chat():
    with db() as conn:
        conn.execute("DELETE FROM chat_log")
