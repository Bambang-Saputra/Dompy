import os

from google import genai
from google.genai import errors, types

import config
from database import KATEGORI, NAMA_HARI, hari_ini, jejak_data, muat_chat, simpan_chat
from tools import TOOLS

GAYA = {
    "santai": "Bahasa santai dan akrab seperti teman dekat. Panggil user 'kamu'. Boleh pakai maksimal 2 emoji per jawaban.",
    "formal": "Bahasa Indonesia baku, sopan, dan profesional. Panggil user 'Anda'. Jangan pakai emoji maupun slang.",
}
MODE = {
    "suportif": "Saat memberi masukan, apresiasi hal yang sudah baik dulu, lalu sampaikan koreksi dengan lembut dan memotivasi.",
    "tegas": "Saat memberi masukan, langsung tunjuk pemborosan dengan lugas dan beri target yang jelas. Tetap sopan, tanpa basa-basi.",
}
KODE_SIBUK = (429, 500, 503, 504)  # error sementara: model penuh, kena limit, atau server lagi gangguan


def load_api_key():
    key = os.environ.get("GEMINI_API_KEY")
    if not key and os.path.exists(".env"):
        with open(".env", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("GEMINI_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
    return key


def buat_client():
    key = load_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY belum diatur. Isi di Colab Secrets, environment variable, atau file .env.")
    # SDK mengulang sendiri request yang gagal karena server sibuk, dengan jeda yang makin lama (1 s, 2 s, ...)
    retry = types.HttpRetryOptions(attempts=config.RETRY_PERCOBAAN, initial_delay=1, max_delay=8,
                                   http_status_codes=list(KODE_SIBUK))
    return genai.Client(api_key=key, http_options=types.HttpOptions(retry_options=retry))


def buat_system_prompt(gaya, mode):
    today = hari_ini()
    return f"""Kamu adalah Dompy, asisten pengelola budget pribadi berbahasa Indonesia.
Hari ini {NAMA_HARI[today.weekday()]}, {today.isoformat()} (WIB).

ATURAN KERJA
1. Semua pencatatan dan perhitungan WAJIB lewat tools. Jangan pernah menghitung sisa budget atau total sendiri; pakai angka dari hasil tools.
2. Ubah nominal informal ke angka bulat: "18rb"/"18k" = 18000, "1,5jt" = 1500000, "gopek" = 500, "goceng" = 5000, "ceban" = 10000, "gocap" = 50000, "cepek" = 100000.
3. Ubah tanggal relatif (kemarin, Sabtu lalu, tanggal 3) ke format YYYY-MM-DD berdasarkan tanggal hari ini.
4. Satu pesan bisa berisi beberapa pengeluaran: panggil catat_pengeluaran untuk setiap item.
5. Kategori yang tersedia: {", ".join(KATEGORI)}. Pakai "Total" untuk budget keseluruhan. Kalau ragu, pilih yang paling masuk akal dan sebutkan kategorinya.
6. Jika user menyebut budget tanpa periode yang jelas, tanyakan dulu: harian, mingguan, bulanan, atau rentang tanggal tertentu.
7. Setelah mencatat pengeluaran, sebutkan sisa budget kategori itu dan jatah per hari jika ada budgetnya. Beri peringatan jika level "waspada" atau "lewat budget". Jika belum ada budget, tawarkan untuk membuatnya.
8. Jika diminta evaluasi, masukan, atau rekap periode, panggil analisis_pengeluaran lalu berikan: ringkasan singkat, 2-4 saran konkret berdasarkan data (sebut item/kategori nyata), dan usulan budget periode berikutnya.
9. Untuk koreksi ("eh salah, harusnya 15rb"), cari ID lewat daftar_transaksi, hapus_transaksi, lalu catat ulang.
10. Fokus pada keuangan pribadi. Topik lain dijawab singkat lalu arahkan kembali. Jangan merekomendasikan saham, kripto, atau produk investasi tertentu.

FORMAT
- Tulis rupiah seperti Rp25.000.
- Jawaban ringkas (maksimal sekitar 6 baris) kecuali user minta detail atau sedang evaluasi.
- Boleh pakai bullet list untuk rekap.

GAYA BAHASA: {GAYA.get(gaya, GAYA["santai"])}
MODE SARAN: {MODE.get(mode, MODE["suportif"])}
"""


def buat_config(gaya=config.GAYA_BAHASA, mode=config.MODE_SARAN, thinking=True):
    return types.GenerateContentConfig(
        system_instruction=buat_system_prompt(gaya, mode),
        tools=TOOLS,
        temperature=config.TEMPERATURE,
        thinking_config=types.ThinkingConfig(thinking_level=config.THINKING_LEVEL)
        if thinking and config.THINKING_LEVEL else None,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=config.MAX_TOOL_CALLS),
    )


def buat_sesi_chat(client, model=config.MODEL_NAME, history=None):
    """Sesi chat baru. Tanpa `history`, riwayat obrolan terakhir dimuat dari database."""
    if history is None:
        history = [types.Content(role="user" if r["role"] == "user" else "model", parts=[types.Part(text=r["content"])])
                   for r in muat_chat()]
    return client.chats.create(model=model, config=buat_config(), history=history)


def tools_terpakai(sesi):
    """Daftar function call pada giliran terakhir, untuk ditampilkan di UI.

    Dibaca dari riwayat chat karena di google-genai 2.x sesi chat menjalankan function calling sendiri
    dan `response.automatic_function_calling_history` dibiarkan kosong.
    """
    riwayat = sesi.get_history()
    awal = 0
    for i, content in enumerate(riwayat):  # cari pesan user (teks) terakhir
        if content.role == "user" and any(p.text for p in content.parts or []):
            awal = i
    calls = []
    for content in riwayat[awal:]:
        for p in content.parts or []:
            if p.function_call:
                args = ", ".join(f"{k}={v!r}" for k, v in (p.function_call.args or {}).items())
                calls.append(f"{p.function_call.name}({args})")
    return calls


def pesan_error(e):
    """Ubah error Gemini jadi pesan yang bisa dipahami user."""
    kode = getattr(e, "code", None)
    if kode == 429:
        return "Kuota Gemini gratisan lagi habis/terlalu sering dipakai. Tunggu sekitar 1 menit lalu kirim ulang ya."
    if kode in KODE_SIBUK:
        return "Server Gemini lagi penuh (semua model yang dicoba sedang sibuk). Coba kirim ulang sebentar lagi ya."
    if kode in (401, 403) or "API key" in str(e):
        return "API key Gemini ditolak. Cek lagi isi `GEMINI_API_KEY`."
    return f"Gagal menghubungi Gemini: {e}"


def tanya_dompy(client, sesi, pesan, gaya=config.GAYA_BAHASA, mode=config.MODE_SARAN):
    """Kirim pesan ke Dompy.

    Kalau model utama sibuk, pesan dikirim ulang ke model cadangan (riwayat obrolan ikut dibawa).
    Mengembalikan (jawaban, daftar_tool_yang_dipanggil, sesi, model_yang_menjawab). `sesi` bisa berganti
    ke model cadangan, jadi simpan lagi nilai kembaliannya.
    """
    model_dicoba = [sesi._model] + [m for m in config.MODEL_CADANGAN if m != sesi._model]
    # Riwayat sebelum pesan ini. Sesi chat mencatat tiap langkah function calling, jadi kalau gagal di tengah,
    # langkah yang setengah jadi tidak ikut dibawa ke model cadangan.
    riwayat_awal = sesi.get_history(curated=True)

    def sesi_bersih(s):
        """Sesi di model yang sama tanpa langkah setengah jadi dari percobaan yang gagal."""
        return buat_sesi_chat(client, s._model, history=list(riwayat_awal))

    error_terakhir = None
    for model in model_dicoba:
        if model != sesi._model:
            sesi = buat_sesi_chat(client, model, history=list(riwayat_awal))
        sebelum = jejak_data()
        for thinking in (True, False):
            try:
                response = sesi.send_message(pesan, config=buat_config(gaya, mode, thinking))
                jawaban = (response.text or "").strip() or "Maaf, aku belum bisa menjawab itu. Coba ulangi dengan kalimat lain ya."
                simpan_chat("user", pesan)
                simpan_chat("assistant", jawaban)
                return jawaban, tools_terpakai(sesi), sesi, model
            except errors.APIError as e:
                error_terakhir = e
                if e.code == 400 and "thinking" in str(e).lower() and thinking:
                    # model ini tidak mendukung thinking_level, ulangi tanpa itu
                    sesi = sesi_bersih(sesi)
                    continue
                break
            except Exception as e:  # koneksi putus, dsb.
                return f"⚠️ Gagal menghubungi Gemini: {e}", [], sesi_bersih(sesi), None
        if jejak_data() != sebelum:
            # Sebagian tool sudah sempat jalan. Jangan kirim ulang supaya transaksi tidak tercatat dobel.
            return ("⚠️ Gemini terputus di tengah jalan, tapi sebagian data sudah sempat tersimpan. "
                    "Cek tab Transaksi dulu sebelum mengirim ulang ya."), [], sesi_bersih(sesi), None
        if getattr(error_terakhir, "code", None) not in KODE_SIBUK + (404,):
            break  # error bukan karena model sibuk/tidak ada, ganti model tidak akan membantu
    return f"⚠️ {pesan_error(error_terakhir)}", [], sesi_bersih(sesi), None
