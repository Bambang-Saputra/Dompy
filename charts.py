from datetime import timedelta

import pandas as pd
import plotly.graph_objects as go

from database import ambil_pengeluaran, hari_ini, rupiah

WARNA_KATEGORI = {
    "Makanan": "#f97316", "Transportasi": "#3b82f6", "Belanja": "#a855f7", "Hiburan": "#ec4899",
    "Tagihan": "#64748b", "Kesehatan": "#14b8a6", "Pendidikan": "#eab308", "Lainnya": "#94a3b8",
}
FONT = "Plus Jakarta Sans, sans-serif"
TEKS_PUDAR = "#6b7570"
GAYA_DASAR = dict(plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", margin=dict(l=4, r=4, t=8, b=4),
                  font=dict(family=FONT, color="#17201b", size=12),
                  hoverlabel=dict(bgcolor="#17201b", font=dict(family=FONT, color="#ffffff"), bordercolor="#17201b"))


def figur_kosong(pesan, tinggi=260):
    fig = go.Figure()
    fig.add_annotation(text=pesan, showarrow=False, font=dict(size=13, color=TEKS_PUDAR))
    fig.update_layout(xaxis_visible=False, yaxis_visible=False, height=tinggi, **GAYA_DASAR)
    return fig


def grafik_kategori():
    today = hari_ini()
    data = ambil_pengeluaran(today.replace(day=1), today)
    if not data:
        return figur_kosong("Belum ada pengeluaran bulan ini.")
    df = pd.DataFrame(data).groupby("category", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
    fig = go.Figure(go.Pie(labels=df["category"], values=df["amount"], hole=0.62, sort=False, direction="clockwise",
                           marker=dict(colors=[WARNA_KATEGORI.get(k, "#94a3b8") for k in df["category"]],
                                       line=dict(color="#ffffff", width=2)),
                           textinfo="none", customdata=[rupiah(v) for v in df["amount"]],
                           hovertemplate="<b>%{label}</b><br>%{customdata} · %{percent}<extra></extra>"))
    fig.update_layout(height=280, showlegend=True,
                      legend=dict(orientation="v", x=1.02, y=0.5, font=dict(size=12), itemclick=False),
                      annotations=[dict(text=f"<span style='font-size:11px;color:{TEKS_PUDAR}'>Total</span><br>"
                                              f"<b>{rupiah(df['amount'].sum())}</b>",
                                        showarrow=False, font=dict(size=15))],
                      **GAYA_DASAR)
    return fig


def grafik_harian(hari=30):
    today = hari_ini()
    mulai = today - timedelta(days=hari - 1)
    data = ambil_pengeluaran(mulai, today)
    if not data:
        return figur_kosong(f"Belum ada pengeluaran {hari} hari terakhir.")
    pivot = pd.DataFrame(data).pivot_table(index="date", columns="category", values="amount", aggfunc="sum", fill_value=0)
    pivot = pivot.reindex([(mulai + timedelta(days=i)).isoformat() for i in range(hari)], fill_value=0)
    tanggal = pd.to_datetime(pivot.index)
    fig = go.Figure()
    for kat in pivot.columns:
        fig.add_bar(x=tanggal, y=pivot[kat], name=kat, marker_color=WARNA_KATEGORI.get(kat, "#94a3b8"),
                    customdata=[rupiah(v) for v in pivot[kat]],
                    hovertemplate=f"{kat}: %{{customdata}}<extra></extra>")
    fig.update_layout(barmode="stack", height=280, bargap=0.25, hovermode="x unified",
                      legend=dict(orientation="h", y=-0.18, font=dict(size=11)),
                      xaxis=dict(showgrid=False, tickformat="%d %b", tickfont=dict(color=TEKS_PUDAR)),
                      yaxis=dict(gridcolor="#eceee9", tickformat="~s", tickprefix="Rp", tickfont=dict(color=TEKS_PUDAR)),
                      **GAYA_DASAR)
    return fig
