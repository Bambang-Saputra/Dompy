from datetime import timedelta
from html import escape

import pandas as pd
import streamlit as st

import agent
import charts
import config
from database import (NAMA_HARI, budget_aktif, hapus_chat, hari_ini, muat_chat, rupiah, status_budget,
                      tambah_bulan, total_pengeluaran)
from tools import daftar_transaksi

st.set_page_config(page_title="Dompy · Asisten Budget", page_icon="💸", layout="wide")

CONTOH_PESAN = [
    "Budget makan minggu ini 300rb",
    "Makan bakso 18rb + es teh 5rb",
    "Kemarin bensin 30rb, parkir goceng",
    "Sisa budget makanku?",
    "Evaluasi pengeluaran bulan ini",
]
IKON = {"Makanan": "🍜", "Transportasi": "🛵", "Belanja": "🛍️", "Hiburan": "🎬", "Tagihan": "🧾",
        "Kesehatan": "💊", "Pendidikan": "📚", "Lainnya": "📦", "Total": "💰"}
WARNA_LEVEL = {"aman": "#0f9d6e", "waspada": "#f59e0b", "lewat budget": "#e5484d"}
NAMA_BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
              "November", "Desember"]

st.html("""<style>
[data-testid="stMainBlockContainer"] {padding-top: 2.2rem; padding-bottom: 2rem; max-width: 1320px;}
[data-testid="stSidebarHeader"] {display: none;}
h1, h2, h3 {letter-spacing: -0.02em;}
.st-key-kartu-chat, .st-key-kartu-budget, .st-key-kartu-grafik {
  background: #fff; border: 1px solid #e2e5df; border-radius: 18px; padding: 1.1rem 1.2rem;
  box-shadow: 0 1px 2px rgba(23,32,27,.04), 0 8px 24px -16px rgba(23,32,27,.12);
}
.judul-kartu {font-weight: 700; font-size: 1rem; margin: 0 0 .15rem 0;}
.sub-kartu {color: #6b7570; font-size: .82rem; margin: 0;}
.sapaan {font-size: 1.85rem; font-weight: 800; letter-spacing: -0.03em; margin: 0; line-height: 1.15;}
.tanggal {color: #6b7570; margin: .25rem 0 0 0; font-size: .95rem;}
.kpi {background: #fff; border: 1px solid #e2e5df; border-radius: 18px; padding: 1rem 1.15rem; height: 100%;}
.kpi.utama {background: linear-gradient(135deg, #0f9d6e 0%, #0b7a56 100%); border: none; color: #fff;}
.kpi .label {font-size: .8rem; font-weight: 600; color: #6b7570; text-transform: uppercase; letter-spacing: .04em;}
.kpi.utama .label, .kpi.utama .delta {color: rgba(255,255,255,.85);}
.kpi .angka {font-size: 1.6rem; font-weight: 800; letter-spacing: -0.03em; margin: .2rem 0 .1rem 0; white-space: nowrap;}
.kpi .delta {font-size: .8rem; color: #6b7570;}
.delta .naik {color: #e5484d; font-weight: 700;} .delta .turun {color: #0f9d6e; font-weight: 700;}
.kpi.utama .delta .naik, .kpi.utama .delta .turun {color: #fff;}
.budget {padding: .8rem 0; border-bottom: 1px solid #eceee9;}
.budget:last-child {border-bottom: none; padding-bottom: 0;}
.budget .atas {display: flex; justify-content: space-between; align-items: baseline; gap: .5rem;}
.budget .nama {font-weight: 700;}
.budget .periode {font-size: .72rem; font-weight: 600; color: #6b7570; background: #f2f4f0;
  padding: .1rem .5rem; border-radius: 999px; margin-left: .35rem; text-transform: capitalize;}
.budget .nominal {font-size: .85rem; color: #6b7570; white-space: nowrap;}
.budget .nominal b {color: #17201b;}
.bar {height: 8px; background: #eceee9; border-radius: 999px; margin: .5rem 0 .4rem 0; overflow: hidden;}
.bar > div {height: 100%; border-radius: 999px;}
.budget .bawah {display: flex; justify-content: space-between; font-size: .78rem; color: #6b7570;}
.kosong {color: #6b7570; font-size: .9rem; padding: 1.2rem 0; text-align: center;}
.logo {display: flex; align-items: center; gap: .6rem; margin: .2rem 0 .3rem 0;}
.logo .ikon {width: 40px; height: 40px; border-radius: 12px; background: #0f9d6e; display: grid;
  place-items: center; font-size: 1.3rem;}
.logo .nama {font-weight: 800; font-size: 1.35rem; letter-spacing: -0.03em;}
.model-info {font-size: .75rem; color: #6b7570;}
[data-testid="stChatMessage"] {background: transparent; padding: .35rem 0;}
.st-key-pilihan-contoh button {font-size: .8rem;}
</style>""")


@st.cache_resource
def get_client():
    return agent.buat_client()


try:
    client = get_client()
except RuntimeError as e:
    st.error(str(e))
    st.stop()

if "sesi" not in st.session_state:
    st.session_state.sesi = agent.buat_sesi_chat(client)
    st.session_state.messages = [{"role": r["role"], "content": r["content"], "tools": []} for r in muat_chat()]


def pilih_contoh():
    st.session_state.kirim = st.session_state["pilihan-contoh"]
    st.session_state["pilihan-contoh"] = None


# ---------- Sidebar ----------
with st.sidebar:
    st.html('<div class="logo"><div class="ikon">💸</div><div class="nama">Dompy</div></div>'
            '<p class="sub-kartu">Catat pengeluaran cukup dengan ngobrol. Gemini yang paham kalimatmu, '
            'Python yang ngitung angkanya.</p>')
    st.divider()
    gaya = st.segmented_control("Gaya bahasa", ["santai", "formal"], default=config.GAYA_BAHASA,
                                format_func=str.capitalize, width="stretch") or config.GAYA_BAHASA
    mode = st.segmented_control("Mode saran", ["suportif", "tegas"], default=config.MODE_SARAN,
                                format_func=str.capitalize, width="stretch") or config.MODE_SARAN
    st.divider()
    if st.button("Mulai obrolan baru", icon=":material/refresh:", width="stretch",
                 help="Riwayat chat dihapus, data budget dan transaksi tetap tersimpan."):
        hapus_chat()
        st.session_state.sesi = agent.buat_sesi_chat(client)
        st.session_state.messages = []
        st.rerun()
    st.html(f'<p class="model-info">Model: <code>{config.MODEL_NAME}</code><br>'
            f'Cadangan: <code>{"</code>, <code>".join(config.MODEL_CADANGAN)}</code></p>')


# ---------- Header + ringkasan ----------
today = hari_ini()


def kartu_kpi(label, sekarang, sebelumnya, pembanding, utama=False):
    if sebelumnya:
        persen = (sekarang - sebelumnya) / sebelumnya * 100
        kelas, panah = ("naik", "▲") if persen > 0 else ("turun", "▼")
        delta = f'<span class="{kelas}">{panah} {abs(persen):.0f}%</span> vs {pembanding}'
    else:
        delta = f"belum ada data {pembanding}"
    return (f'<div class="kpi{" utama" if utama else ""}"><div class="label">{label}</div>'
            f'<div class="angka">{rupiah(sekarang)}</div><div class="delta">{delta}</div></div>')


awal_minggu = today - timedelta(days=today.weekday())
bulan_lalu = tambah_bulan(today, -1)
st.html(f'<p class="sapaan">Halo! Gimana dompetmu hari ini?</p>'
        f'<p class="tanggal">{NAMA_HARI[today.weekday()]}, {today.day} {NAMA_BULAN[today.month - 1]} {today.year}</p>')
k1, k2, k3 = st.columns(3)
k1.html(kartu_kpi("Hari ini", total_pengeluaran(today, today),
                  total_pengeluaran(today - timedelta(days=1), today - timedelta(days=1)), "kemarin"))
k2.html(kartu_kpi("Minggu ini", total_pengeluaran(awal_minggu, today),
                  total_pengeluaran(awal_minggu - timedelta(days=7), today - timedelta(days=7)), "minggu lalu"))
k3.html(kartu_kpi("Bulan ini", total_pengeluaran(today.replace(day=1), today),
                  total_pengeluaran(bulan_lalu.replace(day=1), bulan_lalu), "bulan lalu", utama=True))


def tampilkan_pesan(m):
    with st.chat_message(m["role"], avatar=":material/person:" if m["role"] == "user" else "💸"):
        st.markdown(m["content"])
        if m.get("tools"):
            with st.expander(f"{len(m['tools'])} tool dipanggil", icon=":material/build:"):
                for c in m["tools"]:
                    st.code(c, language="python", wrap_lines=True)
        if m.get("model_cadangan"):
            st.caption(f"Model utama sibuk, pindah ke `{m['model_cadangan']}`.")


# ---------- Chat + dashboard ----------
kiri, kanan = st.columns([1.15, 1], gap="medium")

with kiri:
    with st.container(key="kartu-chat"):
        st.html('<p class="judul-kartu">Ngobrol sama Dompy</p>'
                '<p class="sub-kartu">Tulis budget atau pengeluaran pakai bahasa sehari-hari.</p>')
        kotak_chat = st.container(height=520, border=False)
        st.pills("Contoh", CONTOH_PESAN, key="pilihan-contoh", on_change=pilih_contoh, label_visibility="collapsed")
        prompt = st.chat_input("Contoh: tadi makan nasi padang 22rb") or st.session_state.pop("kirim", None)
        with kotak_chat:
            if not st.session_state.messages and not prompt:
                with st.chat_message("assistant", avatar="💸"):
                    st.markdown("**Halo, aku Dompy!** Mulai dengan kasih tahu budget kamu, lalu ceritakan "
                                "pengeluaranmu kayak lagi chat teman. Contoh: *budget makan minggu ini 300rb*.")
            for m in st.session_state.messages:
                tampilkan_pesan(m)
            if prompt:
                pesan_user = {"role": "user", "content": prompt, "tools": []}
                tampilkan_pesan(pesan_user)
                model_lama = st.session_state.sesi._model
                with st.chat_message("assistant", avatar="💸"):
                    with st.spinner("Dompy lagi nyatet..."):
                        jawaban, calls, st.session_state.sesi, model = agent.tanya_dompy(
                            client, st.session_state.sesi, prompt, gaya, mode)
                # keterangan model cadangan cukup muncul sekali, saat pindahnya terjadi
                pesan_dompy = {"role": "assistant", "content": jawaban, "tools": calls,
                               "model_cadangan": model if model and model != model_lama else None}
                st.session_state.messages += [pesan_user, pesan_dompy]
                st.rerun()  # gambar ulang supaya chat dan dashboard memakai data terbaru


def kartu_budget(s):
    persen = s["persen_terpakai"]
    warna = WARNA_LEVEL[s["level"]]
    if s["level"] == "lewat budget":
        info = f'<span style="color:{warna};font-weight:700">Lewat budget</span>'
    else:
        info = f'Sisa <b>{s["sisa"]}</b> · {s["jatah_per_hari"]}/hari'
    return (f'<div class="budget"><div class="atas"><div><span class="nama">{IKON.get(s["kategori"], "📦")} '
            f'{escape(s["kategori"])}</span><span class="periode">{escape(s["periode"])}</span></div>'
            f'<div class="nominal"><b>{s["terpakai"]}</b> / {s["budget"]}</div></div>'
            f'<div class="bar"><div style="width:{min(persen, 100):.0f}%;background:{warna}"></div></div>'
            f'<div class="bawah"><span>{info}</span><span>{persen:.0f}% · {s["hari_tersisa"]} hari lagi</span>'
            f'</div></div>')


with kanan:
    with st.container(key="kartu-budget"):
        st.html('<p class="judul-kartu">Budget aktif</p><p class="sub-kartu">Hijau aman, kuning waspada (≥75%), '
                'merah lewat budget.</p>')
        semua = sorted((status_budget(b) for b in budget_aktif()), key=lambda s: -s["persen_terpakai"])
        st.html("".join(kartu_budget(s) for s in semua) if semua else
                '<div class="kosong">Belum ada budget aktif.<br>Coba ketik: <i>budget makan minggu ini 300rb</i></div>')

    with st.container(key="kartu-grafik"):
        tab1, tab2, tab3 = st.tabs(["Per kategori", "30 hari terakhir", "Transaksi"])
        with tab1:
            st.plotly_chart(charts.grafik_kategori(), width="stretch", config={"displayModeBar": False})
        with tab2:
            st.plotly_chart(charts.grafik_harian(), width="stretch", config={"displayModeBar": False})
        with tab3:
            rows = daftar_transaksi(30)["transaksi"]
            if rows:
                df = pd.DataFrame(rows)[["id", "tanggal", "kategori", "deskripsi", "jumlah"]]
                df["tanggal"] = pd.to_datetime(df["tanggal"])
                st.dataframe(df, hide_index=True, width="stretch", height=280, column_config={
                    "id": st.column_config.NumberColumn("ID", width="small"),
                    "tanggal": st.column_config.DateColumn("Tanggal", format="DD MMM"),
                    "kategori": "Kategori", "deskripsi": "Keterangan", "jumlah": "Jumlah"})
            else:
                st.html('<div class="kosong">Belum ada transaksi.</div>')
