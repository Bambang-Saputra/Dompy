from collections import Counter, defaultdict
from datetime import date

from database import (NAMA_HARI, ambil_pengeluaran, budget_aktif, db, hari_ini, hitung_periode, ke_tanggal,
                      normalisasi_kategori, periode_sebelumnya, rupiah, sekarang, status_budget)


def atur_budget(category: str, amount: int, period: str, start_date: str = "", end_date: str = "") -> dict:
    """Menyimpan atau mengganti budget untuk satu kategori pengeluaran.

    Args:
        category: Kategori, misalnya Makanan, Transportasi, Belanja, Hiburan, Tagihan, Kesehatan, Pendidikan, Lainnya. Gunakan "Total" untuk budget seluruh pengeluaran.
        amount: Nominal budget dalam rupiah sebagai angka bulat, contoh 300000.
        period: Salah satu dari "harian", "mingguan", "bulanan", atau "custom".
        start_date: Tanggal mulai (YYYY-MM-DD). Kosongkan untuk periode berjalan (hari ini, minggu ini Senin-Minggu, atau bulan ini).
        end_date: Tanggal selesai (YYYY-MM-DD). Hanya diisi untuk period "custom".
    """
    try:
        amount = int(round(float(amount)))
        if amount <= 0:
            return {"status": "gagal", "pesan": "Nominal budget harus lebih dari 0."}
        kategori = normalisasi_kategori(category)
        periode, mulai, selesai = hitung_periode(period, start_date, end_date)
    except ValueError as e:
        return {"status": "gagal", "pesan": str(e)}

    with db() as conn:
        diganti = conn.execute(
            "DELETE FROM budgets WHERE category = ? AND start_date <= ? AND end_date >= ?",
            (kategori, selesai.isoformat(), mulai.isoformat()),
        ).rowcount
        cur = conn.execute(
            "INSERT INTO budgets (category, amount, period, start_date, end_date, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (kategori, amount, periode, mulai.isoformat(), selesai.isoformat(), sekarang()),
        )
        row = conn.execute("SELECT * FROM budgets WHERE id = ?", (cur.lastrowid,)).fetchone()
    hasil = status_budget(dict(row))
    hasil["status"] = "ok"
    hasil["mengganti_budget_lama"] = diganti > 0
    return hasil


def catat_pengeluaran(category: str, amount: int, description: str, expense_date: str = "") -> dict:
    """Mencatat satu pengeluaran dan mengembalikan sisa budget yang terkait. Panggil sekali untuk setiap item.

    Args:
        category: Kategori pengeluaran, misalnya Makanan, Transportasi, Belanja, Hiburan, Tagihan, Kesehatan, Pendidikan, Lainnya.
        amount: Nominal dalam rupiah sebagai angka bulat, contoh 18000.
        description: Keterangan singkat, contoh "bakso" atau "isi bensin".
        expense_date: Tanggal transaksi (YYYY-MM-DD). Kosongkan jika hari ini.
    """
    try:
        amount = int(round(float(amount)))
        if amount <= 0:
            return {"status": "gagal", "pesan": "Nominal pengeluaran harus lebih dari 0."}
        kategori = normalisasi_kategori(category)
        if kategori == "Total":
            kategori = "Lainnya"
        tanggal = ke_tanggal(expense_date)
    except ValueError as e:
        return {"status": "gagal", "pesan": str(e)}

    with db() as conn:
        cur = conn.execute(
            "INSERT INTO expenses (category, amount, description, date, created_at) VALUES (?, ?, ?, ?, ?)",
            (kategori, amount, (description or "").strip(), tanggal.isoformat(), sekarang()),
        )
        expense_id = cur.lastrowid

    terkait = [status_budget(b) for b in budget_aktif(tanggal) if b["category"] in (kategori, "Total")]
    return {
        "status": "ok",
        "id": expense_id,
        "kategori": kategori,
        "jumlah": rupiah(amount),
        "deskripsi": description,
        "tanggal": tanggal.isoformat(),
        "budget_terkait": terkait,
        "catatan": "" if terkait else f"Belum ada budget untuk {kategori} pada tanggal ini.",
    }


def cek_budget(category: str = "") -> dict:
    """Melihat kondisi budget yang sedang aktif hari ini: terpakai, sisa, jatah per hari, dan proyeksi.

    Args:
        category: Nama kategori tertentu. Kosongkan untuk melihat semua budget aktif.
    """
    semua = budget_aktif()
    if category:
        kategori = normalisasi_kategori(category)
        semua = [b for b in semua if b["category"] == kategori]
    if not semua:
        return {"status": "kosong", "pesan": "Belum ada budget aktif" + (f" untuk {category}." if category else ".")}
    return {"status": "ok", "tanggal_hari_ini": hari_ini().isoformat(), "budget": [status_budget(b) for b in semua]}


def ringkasan_pengeluaran(start_date: str = "", end_date: str = "") -> dict:
    """Rekap pengeluaran pada rentang tanggal: total, per kategori, rata-rata harian, dan transaksi terbesar.

    Args:
        start_date: Tanggal awal (YYYY-MM-DD). Kosongkan untuk awal bulan ini.
        end_date: Tanggal akhir (YYYY-MM-DD). Kosongkan untuk hari ini.
    """
    try:
        mulai = ke_tanggal(start_date) if start_date else hari_ini().replace(day=1)
        selesai = ke_tanggal(end_date)
    except ValueError as e:
        return {"status": "gagal", "pesan": str(e)}
    data = ambil_pengeluaran(mulai, selesai)
    if not data:
        return {"status": "kosong", "pesan": f"Tidak ada pengeluaran antara {mulai} dan {selesai}."}
    total = sum(d["amount"] for d in data)
    per_kategori = defaultdict(int)
    for d in data:
        per_kategori[d["category"]] += d["amount"]
    terbesar = max(data, key=lambda d: d["amount"])
    return {
        "status": "ok",
        "rentang": f"{mulai} s/d {selesai}",
        "total": rupiah(total),
        "jumlah_transaksi": len(data),
        "rata_rata_per_hari": rupiah(total / ((selesai - mulai).days + 1)),
        "per_kategori": {k: f"{rupiah(v)} ({v / total * 100:.0f}%)"
                         for k, v in sorted(per_kategori.items(), key=lambda x: -x[1])},
        "transaksi_terbesar": f"{terbesar['description']} ({terbesar['category']}) {rupiah(terbesar['amount'])} pada {terbesar['date']}",
    }


def daftar_transaksi(limit: int = 10, category: str = "") -> dict:
    """Menampilkan transaksi terakhir beserta ID-nya. Dipakai juga untuk mencari transaksi yang mau dikoreksi.

    Args:
        limit: Jumlah transaksi yang ditampilkan, default 10.
        category: Filter kategori. Kosongkan untuk semua kategori.
    """
    sql, args = "SELECT * FROM expenses", []
    if category:
        sql += " WHERE category = ?"
        args.append(normalisasi_kategori(category))
    sql += " ORDER BY date DESC, id DESC LIMIT ?"
    args.append(max(1, min(int(limit), 50)))
    with db() as conn:
        rows = conn.execute(sql, args).fetchall()
    return {"status": "ok", "transaksi": [
        {"id": r["id"], "tanggal": r["date"], "kategori": r["category"],
         "deskripsi": r["description"], "jumlah": rupiah(r["amount"])} for r in rows]}


def hapus_transaksi(expense_id: int) -> dict:
    """Menghapus satu transaksi berdasarkan ID (misalnya karena salah catat).

    Args:
        expense_id: ID transaksi dari daftar_transaksi atau dari hasil catat_pengeluaran.
    """
    with db() as conn:
        row = conn.execute("SELECT * FROM expenses WHERE id = ?", (int(expense_id),)).fetchone()
        if not row:
            return {"status": "gagal", "pesan": f"Transaksi dengan ID {expense_id} tidak ditemukan."}
        conn.execute("DELETE FROM expenses WHERE id = ?", (int(expense_id),))
    return {"status": "ok", "dihapus": f"{row['description']} ({row['category']}) {rupiah(row['amount'])} pada {row['date']}"}


def analisis_pengeluaran(period: str = "bulanan") -> dict:
    """Mengumpulkan data evaluasi periode berjalan sebagai bahan masukan dan rekomendasi.

    Hasilnya berisi perbandingan dengan periode sebelumnya per kategori, kepatuhan terhadap budget,
    item yang paling sering dibeli, hari paling boros, pola weekday vs weekend, serta rata-rata 3 periode
    terakhir per kategori yang bisa dipakai untuk mengusulkan budget periode berikutnya.

    Args:
        period: "mingguan" atau "bulanan".
    """
    try:
        nama, mulai, selesai = hitung_periode(period)
    except ValueError as e:
        return {"status": "gagal", "pesan": str(e)}
    sampai = min(selesai, hari_ini())
    data = ambil_pengeluaran(mulai, sampai)
    prev_mulai, prev_selesai = periode_sebelumnya(mulai, selesai)

    def per_kat(rows):
        hasil = defaultdict(int)
        for r in rows:
            hasil[r["category"]] += r["amount"]
        return hasil

    now_k, prev_k = per_kat(data), per_kat(ambil_pengeluaran(prev_mulai, prev_selesai))
    perbandingan = {}
    for k in sorted(set(now_k) | set(prev_k), key=lambda k: -now_k.get(k, 0)):
        a, b = now_k.get(k, 0), prev_k.get(k, 0)
        perbandingan[k] = {"periode_ini": rupiah(a), "periode_lalu": rupiah(b),
                           "perubahan": f"{(a - b) / b * 100:+.0f}%" if b else "baru"}

    # rata-rata 3 periode penuh sebelumnya, bahan usulan budget
    riwayat = defaultdict(list)
    m, s = mulai, selesai
    for _ in range(3):
        m, s = periode_sebelumnya(m, s)
        kat = per_kat(ambil_pengeluaran(m, s))
        for k in set(kat) | set(now_k):
            riwayat[k].append(kat.get(k, 0))
    rata3 = {k: rupiah(sum(v) / len(v)) for k, v in riwayat.items() if sum(v) > 0}

    item = Counter((r["description"] or "").strip().lower() for r in data if r["description"])
    per_hari = defaultdict(int)
    for r in data:
        per_hari[r["date"]] += r["amount"]
    weekday = [v for d, v in per_hari.items() if date.fromisoformat(d).weekday() < 5]
    weekend = [v for d, v in per_hari.items() if date.fromisoformat(d).weekday() >= 5]
    terboros = max(per_hari.items(), key=lambda x: x[1]) if per_hari else None

    total = sum(now_k.values())
    hari_berjalan = (sampai - mulai).days + 1
    return {
        "status": "ok" if data else "kosong",
        "periode": nama,
        "rentang": f"{mulai} s/d {selesai} (data sampai {sampai})",
        "hari_berjalan": hari_berjalan,
        "total_periode_ini": rupiah(total),
        "total_periode_lalu": rupiah(sum(prev_k.values())),
        "rata_rata_per_hari": rupiah(total / hari_berjalan),
        "per_kategori": perbandingan,
        "status_budget": [status_budget(b) for b in budget_aktif(sampai)],
        "item_paling_sering": [f"{n} ({c}x)" for n, c in item.most_common(5)],
        "hari_terboros": f"{NAMA_HARI[date.fromisoformat(terboros[0]).weekday()]} {terboros[0]}: {rupiah(terboros[1])}" if terboros else "-",
        "rata_rata_harian_weekday": rupiah(sum(weekday) / len(weekday)) if weekday else rupiah(0),
        "rata_rata_harian_weekend": rupiah(sum(weekend) / len(weekend)) if weekend else rupiah(0),
        "rata_rata_3_periode_sebelumnya": rata3,
    }


TOOLS = [atur_budget, catat_pengeluaran, cek_budget, ringkasan_pengeluaran,
         daftar_transaksi, hapus_transaksi, analisis_pengeluaran]
