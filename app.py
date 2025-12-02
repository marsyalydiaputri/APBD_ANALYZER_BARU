# app.py
import streamlit as st
import pandas as pd
import numpy as np
import io
import re
import plotly.express as px
from sklearn.ensemble import IsolationForest

st.set_page_config(page_title="APBD Analyzer — Rasio, Interpretasi & Fraud Detection", layout="wide")
st.title("📊 APBD Analyzer — Rasio, Interpretasi & Fraud Detection")

# -----------------------
# Template Excel
# -----------------------
TEMPLATE_COLUMNS = ["Akun","Anggaran","Realisasi","Persentase","Tahun"]
SAMPLE_ROWS = [
    ["Pendapatan Daerah", 3557491170098, 3758774961806, 105.66, 2024],
    ["PAD", 322846709929, 561854145372, 174.03, 2024],
    ["Belanja Pegawai", 1161122041234, 1058941535362, 91.20, 2024],
    ["Belanja Modal", 1133163195359, 836917297001, 73.86, 2024],
]

def make_template_excel():
    df = pd.DataFrame(SAMPLE_ROWS, columns=TEMPLATE_COLUMNS)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="APBD")
    buffer.seek(0)
    return buffer

# -----------------------
# Utilities
# -----------------------
def parse_number(x):
    if pd.isna(x): return 0.0
    if isinstance(x, (int,float,np.integer,np.floating)): return float(x)
    s = str(x).strip()
    if s == "": return 0.0
    if s.startswith("(") and s.endswith(")"): s = "-" + s[1:-1]
    s = s.replace("Rp","").replace("rp","").replace(" ","")
    if "." in s and "," in s: s = s.replace(".","").replace(",",".")
    else:
        if "." in s and re.search(r"\.\d{1,2}$", s) is None: s = s.replace(".","")
        s = s.replace(",",".")
    s = re.sub(r"[^\d\.\-]", "", s)
    if s in ("","-","."): return 0.0
    try: return float(s)
    except: return 0.0

def format_rupiah(x):
    try:
        v = int(round(float(x)))
        return f"{v:,}".replace(",",".")
    except: return x

def find_column_by_keywords(df, keywords):
    cols = df.columns.astype(str).tolist()
    for k in keywords:
        for c in cols:
            if k.lower() in c.lower(): return c
    return None

def classify_account(name):
    if not isinstance(name,str): name=str(name)
    n = name.lower()
    if "pad" in n or "pajak" in n or "retribusi" in n: return "PAD"
    if "tkdd" in n or "transfer" in n or "dau" in n or "dak" in n or "dbh" in n: return "TRANSFER"
    if n.strip().startswith("pendapatan") or "pendapatan daerah" in n: return "PENDAPATAN"
    if "belanja pegawai" in n or "belanja barang" in n or "belanja jasa" in n: return "BELANJA_OPERASI"
    if "belanja modal" in n or ("modal" in n and "belanja" in n): return "BELANJA_MODAL"
    if "hibah" in n or "bantuan" in n or "subsidi" in n or "bagi hasil" in n: return "BELANJA_LAINNYA"
    if "tidak terduga" in n: return "BELANJA_TIDAK_TERDUGA"
    if "pembiayaan" in n or "sisa lebih" in n: return "PEMBIAYAAN"
    return "LAINNYA"

def safe_pct(a,b):
    try: return (a/b*100) if b and b!=0 else 0.0
    except: return 0.0

def compute_ratios(agg_df, full_df, prev_agg=None):
    totals={}
    def get_sum(cat):
        return float(agg_df.loc[agg_df['Kategori']==cat,'Realisasi'].sum()) if cat in agg_df['Kategori'].values else 0.0
    totals['PAD'] = get_sum('PAD')
    totals['TRANSFER'] = get_sum('TRANSFER')
    totals['PENDAPATAN'] = get_sum('PENDAPATAN')
    totals['BEL_OP'] = get_sum('BELANJA_OPERASI')
    totals['BEL_MOD'] = get_sum('BELANJA_MODAL')
    totals['TOTAL_BELANJA'] = agg_df[agg_df['Kategori'].str.contains('BELANJA', na=False)]['Realisasi'].sum() if agg_df['Kategori'].str.contains('BELANJA', na=False).any() else 0.0
    totals['ANGGARAN_TOTAL'] = full_df['Anggaran_num'].sum()
    totals['REALISASI_TOTAL'] = full_df['Realisasi_num'].sum()
    totals['BELANJA_PEG'] = full_df[full_df['Akun'].str.lower().str.contains('pegawai', na=False)]['Realisasi_num'].sum()
    totals['BELANJA_BARANG'] = full_df[full_df['Akun'].str.lower().str.contains('barang', na=False)]['Realisasi_num'].sum()
    totals['SILPA'] = totals['ANGGARAN_TOTAL'] - totals['REALISASI_TOTAL']
    ratios={}
    ratios['Rasio Kemandirian (PAD/Transfer) %'] = safe_pct(totals['PAD'],totals['TRANSFER'])
    ratios['Rasio Ketergantungan Transfer (%)'] = safe_pct(totals['TRANSFER'], totals['PENDAPATAN'] if totals['PENDAPATAN']>0 else totals['PAD']+totals['TRANSFER'])
    ratios['Rasio Efektivitas Pendapatan (%)'] = safe_pct(totals['REALISASI_TOTAL'],totals['ANGGARAN_TOTAL'])
    ratios['Rasio Efisiensi Belanja (%)'] = safe_pct(totals['REALISASI_TOTAL'],totals['ANGGARAN_TOTAL'])
    ratios['Rasio Belanja Operasi (%)'] = safe_pct(totals['BEL_OP'],totals['TOTAL_BELANJA'])
    ratios['Rasio Belanja Modal (%)'] = safe_pct(totals['BEL_MOD'],totals['TOTAL_BELANJA'])
    ratios['Rasio Belanja Pegawai / Total Belanja (%)'] = safe_pct(totals['BELANJA_PEG'],totals['TOTAL_BELANJA'])
    ratios['Rasio Belanja Barang/Jasa / Total Belanja (%)'] = safe_pct(totals['BELANJA_BARANG'],totals['TOTAL_BELANJA'])
    ratios['SILPA (Rupiah)'] = totals['SILPA']
    if prev_agg is not None:
        prev_total = prev_agg['Realisasi'].sum() if 'Realisasi' in prev_agg.columns else 0.0
        ratios['Pertumbuhan Realisasi (%)'] = safe_pct(totals['REALISASI_TOTAL']-prev_total, prev_total if prev_total>0 else 1.0)
    else: ratios['Pertumbuhan Realisasi (%)']=None
    return ratios,totals

def interpret_ratios(ratios):
    texts=[]
    k=ratios.get('Rasio Kemandirian (PAD/Transfer) %',0.0)
    if k<10: texts.append(f"Rasio kemandirian {k:.2f}% — sangat rendah; daerah sangat bergantung pada transfer pusat.")
    elif k<20: texts.append(f"Rasio kemandirian {k:.2f}% — rendah; perlu peningkatan PAD.")
    elif k<50: texts.append(f"Rasio kemandirian {k:.2f}% — sedang; ada kapasitas PAD namun perlu penguatan.")
    else: texts.append(f"Rasio kemandirian {k:.2f}% — tinggi; daerah relatif mandiri.")
    ef=ratios.get('Rasio Efektivitas Pendapatan (%)',0.0)
    if ef<80: texts.append(f"Efektivitas pendapatan {ef:.2f}% — realisasi di bawah target; perlu evaluasi.")
    elif ef<=100: texts.append(f"Efektivitas pendapatan {ef:.2f}% — sesuai target.")
    else: texts.append(f"Efektivitas pendapatan {ef:.2f}% — melebihi target; verifikasi kewajaran target.")
    bo=ratios.get('Rasio Belanja Operasi (%)',0.0)
    bm=ratios.get('Rasio Belanja Modal (%)',0.0)
    texts.append(f"Komposisi belanja: operasi {bo:.2f}% — modal {bm:.2f}% (perhatikan proporsi investasi).")
    silpa=ratios.get('SILPA (Rupiah)',0.0)
    if silpa and abs(silpa)>0: texts.append(f"Terdapat SILPA sebesar {format_rupiah(silpa)} — analisis penyebab diperlukan (serapan/anggaran).")
    return "\n\n".join(texts)

# -----------------------
# Fraud Detection AI + rules
# -----------------------
def fraud_checks_ai(df):
    # simple Isolation Forest on Anggaran/Realisasi
    clf = IsolationForest(contamination=0.05, random_state=42)
    df_model = df[['Anggaran_num','Realisasi_num']].copy()
    df_model.fillna(0,inplace=True)
    clf.fit(df_model)
    df['anomaly_score'] = clf.decision_function(df_model)
    df['anomaly_flag'] = clf.predict(df_model)  # -1 anomaly, 1 normal
    df['fraud_status'] = np.where(df['anomaly_flag']==-1,'Mencurigakan','Normal')
    return df

# -----------------------
# Sidebar & Menu
# -----------------------
st.sidebar.header("Kontrol")
menu = st.sidebar.selectbox("Menu", ["Home","Upload & Analyze","Download Template","About"])

if menu=="Home":
    st.header("APBD Analyzer")
    st.markdown("Aplikasi ini menerima file Excel APBD, membersihkan angka, mengelompokkan akun, menghitung rasio keuangan, memberi interpretasi otomatis, dan mendeteksi indikasi fraud/potential anomalies.")
    st.info("Gunakan menu 'Download Template' jika perlu contoh format.")

elif menu=="Download Template":
    st.header("Download Template Excel")
    buf=make_template_excel()
    st.download_button("Download template_apbd.xlsx", data=buf, file_name="template_apbd.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.write("Template contoh: header Akun | Anggaran | Realisasi | Persentase | Tahun")

elif menu=="About":
    st.header("Tentang Aplikasi")
    st.write("""
    APBD Analyzer — versi final.
    - Auto-clean angka (titik/koma/Rp)  
    - Auto-classify akun  
    - Banyak rasio penting  
    - Interpretasi rule-based (offline)  
    - Fraud detection: rules + outlier + AI (Isolation Forest)
    """)

# -----------------------
# Upload & Analyze
# -----------------------
if menu=="Upload & Analyze":
    st.header("Upload file Excel APBD")
    uploaded=st.file_uploader("Pilih file .xlsx", type=["xlsx","xls"])
    if uploaded is None: st.stop()

    try: raw=pd.read_excel(uploaded, sheet_name=0, dtype=str)
    except Exception as e: st.error("Gagal membaca file Excel: "+str(e)); st.stop()

    st.subheader("Preview data mentah (5 baris)")
    st.dataframe(raw.head())

    # detect columns
    akun_col=find_column_by_keywords(raw, ["akun","uraian","rekening","keterangan","nama akun"]) or raw.columns[0]
    anggaran_col=find_column_by_keywords(raw, ["anggaran","pagu","nilai anggaran","budget","anggaran (rp)"])
    realisasi_col=find_column_by_keywords(raw, ["realisasi","realisasi (rp)","realisasi anggaran","realisasi (%)"])
    persen_col=find_column_by_keywords(raw, ["persentase","persen","%"])
    tahun_col=find_column_by_keywords(raw, ["tahun","periode"])

    df = raw.copy()
    df.rename(columns={akun_col:"Akun"}, inplace=True)
    df['Anggaran_raw'] = df[anggaran_col].astype(str)
    df['Realisasi_raw'] = df[realisasi_col].astype(str)
    df['Anggaran_num'] = df['Anggaran_raw'].apply(parse_number)
    df['Realisasi_num'] = df['Realisasi_raw'].apply(parse_number)
    df['Persentase_calc'] = np.where(df['Anggaran_num']>0, df['Realisasi_num']/df['Anggaran_num']*100,0.0)
    if tahun_col: df['Tahun'] = df[tahun_col].astype(str)
    else: df['Tahun']=None
    df['Kategori'] = df['Akun'].apply(classify_account)

    st.subheader("Data setelah cleaning & kategorisasi (contoh 50 baris)")
    show_df=df[['Akun','Anggaran_num','Realisasi_num','Persentase_calc','Kategori','Tahun']].copy()
    show_df.columns=['Akun','Anggaran','Realisasi','Persentase(%)','Kategori','Tahun']
    show_df['Anggaran_fmt']=show_df['Anggaran'].apply(format_rupiah)
    show_df['Realisasi_fmt']=show_df['Realisasi'].apply(format_rupiah)
    st.dataframe(show_df.head(50))

    # aggregate
    agg=df.groupby('Kategori').agg({'Anggaran_num':'sum','Realisasi_num':'sum'}).reset_index().rename(columns={'Anggaran_num':'Anggaran','Realisasi_num':'Realisasi'})
    st.subheader("Aggregasi per Kategori")
    agg_show=agg.copy()
    agg_show['Anggaran_fmt']=agg_show['Anggaran'].apply(format_rupiah)
    agg_show['Realisasi_fmt']=agg_show['Realisasi'].apply(format_rupiah)
    st.dataframe(agg_show)

    # compute ratios
    ratios,totals=compute_ratios(agg,df)
    st.subheader("Hasil Rasio")
    for k,v in ratios.items():
        if v is None: st.write(f"- *{k}*: -")
        else:
            if 'Rasio' in k or 'Pertumbuhan' in k: st.write(f"- *{k}*: {v:.2f}%")
            elif k=='SILPA (Rupiah)': st.write(f"- *{k}*: {format_rupiah(v)}")
            else: st.write(f"- *{k}*: {v}")

    # interpretation
    st.subheader("Interpretasi Otomatis (Offline)")
    interp=interpret_ratios(ratios)
    st.write(interp)

    # Fraud Detection AI
    st.subheader("Fraud Detection — AI + Rules")
    df = fraud_checks_ai(df)
    st.dataframe(df[['Akun','Anggaran_num','Realisasi_num','Kategori','fraud_status']].sort_values(by='fraud_status', ascending=False))

    # visual: composition
    st.subheader("Visual: Komposisi Belanja (Realisasi)")
    BO=totals.get('BEL_OP',0.0)
    BM=totals.get('BEL_MOD',0.0)
    TOTAL_BELANJA=totals.get('TOTAL_BELANJA',0.0)
    comp=pd.DataFrame({'Kategori':['Belanja Operasi','Belanja Modal','Lainnya'],'Nilai':[BO,BM,max(0,TOTAL_BELANJA-BO-BM)]})
    fig=px.pie(comp,names='Kategori',values='Nilai',title='Komposisi Belanja (Realisasi)')
    st.plotly_chart(fig,use_container_width=True)

    if df['Tahun'].notnull().any():
        try:
            pivot=df.groupby('Tahun').agg({'Realisasi_num':'sum'}).reset_index()
            pivot.columns=['Tahun','Total_Realisasi']
            figt=px.line(pivot,x='Tahun',y='Total_Realisasi',title='Tren Realisasi per Tahun')
            st.plotly_chart(figt,use_container_width=True)
        except Exception: pass

    # download aggregated CSV
    st.subheader("Download hasil (CSV)")
    out=agg.copy()
    out['Realisasi']=out['Realisasi'].astype(float)
    out['Anggaran']=out['Anggaran'].astype(float)
    csv=out.to_csv(index=False).encode('utf-8')
    st.download_button("Download aggregated CSV", data=csv, file_name="apbd_aggregated.csv", mime="text/csv")
