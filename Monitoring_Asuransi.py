from datetime import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ---------------------------------------------------------
# 1. Konfigurasi Halaman Dashboard
# ---------------------------------------------------------
st.set_page_config(
    page_title="MSS Insurance Claim & SLA Dashboard",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ MSS Insurance Claim & SLA Tracking Dashboard")
st.caption("Live Connection Google Sheets (Google Form) & Otomatisasi SLA")

SHEET_ID = "15jMIWecycZgWFJ4zWMRNp8FCT5umgqdok_hF2ByHTeQ"
GID = "1414464208"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"


# ---------------------------------------------------------
# 2. Function Parsing Tanggal & Kalkulasi Aging
# ---------------------------------------------------------
def parse_mixed_date(date_val):
  if pd.isna(date_val) or str(date_val).strip() == "" or str(date_val).strip().lower() == "nan":
    return pd.NaT
  
  try:
    parsed = pd.to_datetime(date_val, errors="coerce", dayfirst=True)
    if not pd.isna(parsed):
      return parsed
  except Exception:
    pass

  date_str = str(date_val).strip().split()[0]
  for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d-%m-%y", "%d-%b-%Y", "%d-%b-%y"):
    try:
      return pd.to_datetime(date_str, format=fmt)
    except (ValueError, TypeError):
      continue
  return pd.to_datetime(date_str, dayfirst=True, errors="coerce")


@st.cache_data(ttl=30)
def load_and_process_google_sheet():
  df = pd.read_csv(CSV_URL)
  df.columns = df.columns.astype(str).str.strip()

  # Deteksi kolom Tanggal Insiden secara aman (berdasarkan keyword atau fallback ke indeks kolom)
  incident_candidates = [c for c in df.columns if any(k in c.lower() for k in ["insiden", "kejadian", "incident"])]
  col_incident = incident_candidates[0] if incident_candidates else (df.columns[5] if len(df.columns) > 5 else df.columns[0])

  lappol_candidates = [c for c in df.columns if any(k in c.lower() for k in ["polisi", "lappol", "lap_pol"])]
  col_lappol = lappol_candidates[0] if lappol_candidates else (df.columns[7] if len(df.columns) > 7 else df.columns[1])

  submit_candidates = [c for c in df.columns if any(k in c.lower() for k in ["submit", "submission"])]
  col_submit_date = submit_candidates[0] if submit_candidates else None

  # Eksekusi Parsing Tanggal
  df["_Insiden_Parsed"] = df[col_incident].apply(parse_mixed_date) if col_incident in df.columns else pd.NaT
  df["_LapPol_Parsed"] = df[col_lappol].apply(parse_mixed_date) if col_lappol in df.columns else pd.NaT

  if col_submit_date and col_submit_date in df.columns:
    df["_Submit_Parsed"] = df[col_submit_date].apply(parse_mixed_date)
  else:
    df["_Submit_Parsed"] = pd.NaT

  today = pd.Timestamp(datetime.now().date())

  df["_Insiden_Valid"] = df["_Insiden_Parsed"].apply(
      lambda x: x if pd.isna(x) or x <= today else pd.NaT
  )
  df["_LapPol_Valid"] = df["_LapPol_Parsed"].apply(
      lambda x: x if pd.isna(x) or x <= today else pd.NaT
  )
  df["_Submit_Valid"] = df["_Submit_Parsed"].apply(
      lambda x: x if pd.isna(x) or x <= today else pd.NaT
  )

  # A. Aging Incident (Hari dari Insiden s.d. Hari Ini)
  df["Aging Incident (Hari)"] = (today - df["_Insiden_Valid"]).dt.days
  mask_fb = df["Aging Incident (Hari)"].isna() & df["_Insiden_Parsed"].notna()
  df.loc[mask_fb, "Aging Incident (Hari)"] = (today - df.loc[mask_fb, "_Insiden_Parsed"]).dt.days

  # B. Cek status submission
  def get_submission_status(row):
    raw_sub_val = row[col_submit_date] if (col_submit_date and col_submit_date in df.columns) else None
    parsed_sub = row["_Submit_Parsed"]

    if pd.isna(raw_sub_val) or str(raw_sub_val).strip() == "" or str(raw_sub_val).strip().lower() == "nan":
      return "Belum Submit"
    if not pd.isna(parsed_sub) and parsed_sub > today:
      return "Salah Input Tanggal"
    return "Sudah Submit"

  df["Status Submission"] = df.apply(get_submission_status, axis=1)

  # C. Klasifikasi Status Aging / Scoreboard:
  def get_scoreboard_status(row):
    sub_stat = row["Status Submission"]
    aging = row["Aging Incident (Hari)"]

    if sub_stat == "Sudah Submit":
      return "Sudah Submit Asuransi"
    
    if pd.isna(aging):
      return "Reminding Harus Dikirim (Belum Submit)"
    
    if aging > 30:
      return "Expired"
    elif aging > 14:
      return "Warning (Submit Soon)"
    else:
      return "Prepare submit"

  df["Status Aging Pelaporan"] = df.apply(get_scoreboard_status, axis=1)

  # D. Aging Pelaporan Polisi & Aging Submission
  df["Aging Pelaporan (Hari)"] = (today - df["_LapPol_Valid"]).dt.days
  mask_lappol_fb = df["Aging Pelaporan (Hari)"].isna() & df["_LapPol_Parsed"].notna()
  df.loc[mask_lappol_fb, "Aging Pelaporan (Hari)"] = (today - df.loc[mask_lappol_fb, "_LapPol_Parsed"]).dt.days
  
  def get_aging_sub_val(row):
    parsed_sub = row["_Submit_Valid"]
    if not pd.isna(parsed_sub):
      return (today - parsed_sub).days
    return np.nan

  df["Aging Submission (Hari)"] = df.apply(get_aging_sub_val, axis=1)

  return df, today


try:
  df, today_date = load_and_process_google_sheet()

  # ---------------------------------------------------------
  # 3. Sidebar Filter Utama
  # ---------------------------------------------------------
  st.sidebar.header("🔍 Filter Dashboard")
  st.sidebar.info(f"📅 **Tanggal System:**\n{today_date.strftime('%d %B %Y')}")

  if st.sidebar.button("🔄 Refresh Data Form"):
    st.cache_data.clear()
    st.rerun()

  selected_prov = st.sidebar.multiselect(
      "Pilih Provinsi",
      options=df["Provinsi"].dropna().unique() if "Provinsi" in df.columns else [],
      default=df["Provinsi"].dropna().unique() if "Provinsi" in df.columns else [],
  )

  selected_status = st.sidebar.multiselect(
      "Pilih Status Scoreboard",
      options=df["Status Aging Pelaporan"].unique(),
      default=df["Status Aging Pelaporan"].unique(),
  )

  df_filtered = df.copy()
  if "Provinsi" in df.columns and selected_prov:
    df_filtered = df_filtered[df_filtered["Provinsi"].isin(selected_prov)]
  if selected_status:
    df_filtered = df_filtered[df_filtered["Status Aging Pelaporan"].isin(selected_status)]

  # ---------------------------------------------------------
  # 4. Top Metric Scoreboard
  # ---------------------------------------------------------
  total_site = len(df_filtered)
  count_prepare = len(df_filtered[df_filtered["Status Aging Pelaporan"] == "Prepare submit"])
  count_warning = len(df_filtered[df_filtered["Status Aging Pelaporan"] == "Warning (Submit Soon)"])
  count_expired = len(df_filtered[df_filtered["Status Aging Pelaporan"] == "Expired"])
  count_sudah_submit = len(df_filtered[df_filtered["Status Aging Pelaporan"] == "Sudah Submit Asuransi"])
  count_reminder = len(df_filtered[df_filtered["Status Submission"] == "Belum Submit"])

  m1, m2, m3, m4 = st.columns(4)
  m1.metric("Total Site Insiden", f"{total_site} Site")
  m2.metric("🟢 Prepare Submit (<14 hr)", f"{count_prepare} Site")
  m3.metric("🟡 Warning / Submit Soon (>14-30 hr)", f"{count_warning} Site")
  m4.metric("🔴 Expired (>30 hr)", f"{count_expired} Site")

  s1, s2 = st.columns(2)
  s1.metric("✅ Sudah Submit Asuransi", f"{count_sudah_submit} Site")
  s2.metric("🔔 Reminding Harus Dikirim (Belum Submit)", f"{count_reminder} Site")

  st.markdown("---")

  # ---------------------------------------------------------
  # 5. Visualisasi Charts
  # ---------------------------------------------------------
  c1, c2 = st.columns(2)

  with c1:
    st.subheader("📊 Distribusi Status Scoreboard")
    color_map = {
        "Prepare submit": "#2ecc71",
        "Warning (Submit Soon)": "#f1c40f",
        "Expired": "#e74c3c",
        "Sudah Submit Asuransi": "#3498db",
        "Reminding Harus Dikirim (Belum Submit)": "#95a5a6",
    }
    fig_pie = px.pie(
        df_filtered,
        names="Status Aging Pelaporan",
        color="Status Aging Pelaporan",
        color_discrete_map=color_map,
        hole=0.45,
    )
    st.plotly_chart(fig_pie, use_container_width=True)

  with c2:
    st.subheader("📈 Rata-Rata Aging per Provinsi")
    if "Provinsi" in df_filtered.columns:
      df_avg = (
          df_filtered.groupby("Provinsi")[
              ["Aging Incident (Hari)", "Aging Pelaporan (Hari)"]
          ]
          .mean()
          .reset_index()
      )
      fig_bar = px.bar(
          df_avg,
          x="Provinsi",
          y=["Aging Incident (Hari)", "Aging Pelaporan (Hari)"],
          barmode="group",
          title="Rata-rata Aging Incident vs Pelaporan",
      )
      st.plotly_chart(fig_bar, use_container_width=True)
    else:
      st.info("Kolom Provinsi tidak ditemukan pada data.")

  # ---------------------------------------------------------
  # Analisis Top 5 Material Kehilangan & BOQ
  # ---------------------------------------------------------
  st.markdown("---")
  st.subheader("🛠️ Analisis Top 5 Material Kehilangan & BOQ")

  material_cols = [
      c for c in df.columns 
      if any(k in c.lower() for k in ["material", "barang", "item", "perangkat", "kerugian"])
      and not any(exc in c.lower() for exc in ["upload", "link", "url", "pdf", "berita", "surat"])
  ]
  
  boq_price_cols = [
      c for c in df.columns 
      if any(k in c.lower() for k in ["boq", "harga", "cost", "nilai", "amount", "total"])
      and not any(exc in c.lower() for exc in ["upload", "link", "url"])
  ]

  col_mat = material_cols[0] if material_cols else None
  col_price = boq_price_cols[0] if boq_price_cols else None

  mc1, mc2 = st.columns(2)

  with mc1:
    if col_mat and col_mat in df_filtered.columns:
      st.markdown(f"##### Bar Chart: Top Material Berdasarkan ({col_mat})")
      top_materials = df_filtered[col_mat].value_counts().reset_index()
      top_materials.columns = ['Material', 'Jumlah']
      top5_mat = top_materials.head(5)
      
      fig_mat = px.bar(
          top5_mat, 
          x='Material', 
          y='Jumlah', 
          title="Top Material Kehilangan",
          text='Jumlah',
          color='Jumlah',
          color_continuous_scale='Blues'
      )
      st.plotly_chart(fig_mat, use_container_width=True)
    else:
      st.info("Kolom kategori Material Kehilangan spesifik belum terdeteksi pada form Google Sheet.")

  with mc2:
    if col_mat and col_price:
      st.markdown(f"##### Tabel: Top Material BOQ ({col_price})")
      df_boq = df_filtered.copy()
      df_boq[col_price] = pd.to_numeric(
          df_boq[col_price].astype(str).str.replace(r'[^0-9.]', '', regex=True), 
          errors='coerce'
      )
      
      boq_summary = df_boq.groupby(col_mat)[col_price].mean().reset_index()
      boq_summary.columns = ['Material', 'Harga/Nilai BOQ']
      top5_boq = boq_summary.sort_values(by='Harga/Nilai BOQ', ascending=False).head(5)
      
      st.dataframe(top5_boq.style.format({'Harga/Nilai BOQ': 'Rp {:,.2f}'}), use_container_width=True)
    else:
      st.info("Kolom Nilai/Harga BOQ belum terdeteksi secara otomatis.")

  # ---------------------------------------------------------
  # 6. Tabel Detail dengan 2 Filter
  # ---------------------------------------------------------
  st.markdown("---")
  st.subheader("📋 Detail Status & Aging Site (Form Original Columns)")

  col_f1, col_f2 = st.columns(2)
  with col_f1:
    unique_statuses = ["Semua"] + list(
        df_filtered["Status Aging Pelaporan"].unique()
    )
    table_status_filter = st.selectbox(
        "🔍 1. Filter Berdasarkan Status Scoreboard", unique_statuses
    )

  with col_f2:
    unique_sub_statuses = ["Semua"] + list(
        df_filtered["Status Submission"].unique()
    )
    table_sub_filter = st.selectbox(
        "🔍 2. Filter Berdasarkan Status Submission", unique_sub_statuses
    )

  df_table_final = df_filtered.copy()
  if table_status_filter != "Semua":
    df_table_final = df_table_final[
        df_table_final["Status Aging Pelaporan"] == table_status_filter
    ]
  if table_sub_filter != "Semua":
    df_table_final = df_table_final[
        df_table_final["Status Submission"] == table_sub_filter
    ]

  original_form_cols = [
      c for c in df.columns if not c.startswith("_") and c not in [
          "Aging Incident (Hari)",
          "Aging Pelaporan (Hari)",
          "Status Aging Pelaporan",
          "Status Submission",
          "Aging Submission (Hari)",
      ]
  ]

  added_cols = [
      "Aging Incident (Hari)",
      "Aging Pelaporan (Hari)",
      "Status Aging Pelaporan",
      "Status Submission",
      "Aging Submission (Hari)",
  ]

  df_table_display = df_table_final[original_form_cols + added_cols].copy()

  st.dataframe(
      df_table_display.style.format(
          {
              "Aging Incident (Hari)": "{:.0f}",
              "Aging Pelaporan (Hari)": "{:.0f}",
              "Aging Submission (Hari)": "{:.0f}",
          },
          na_rep="-",
      ).map(
          lambda val: (
              "background-color: #ffcdd2; color: #b71c1c; font-weight: bold;"
              if val == "Expired"
              else (
                  "background-color: #fff9c4; color: #f57f17;"
                  if val == "Warning (Submit Soon)"
                  else (
                      "background-color: #c8e6c9; color: #2e7d32;"
                      if val in ["Prepare submit", "Sudah Submit Asuransi"]
                      else (
                          "background-color: #ffebee; color: #c62828;"
                          if val in ["Belum Submit", "Salah Input Tanggal"]
                          else ""
                      )
                  )
              )
          ),
          subset=["Status Aging Pelaporan", "Status Submission"],
      ),
      use_container_width=True,
      height=500,
  )

except Exception as e:
  st.error("Terjadi kendala pada script dashboard:")
  st.exception(e)