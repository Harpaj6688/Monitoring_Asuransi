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
  if pd.isna(date_val) or str(date_val).strip() == "":
    return pd.NaT
  date_str = str(date_val).strip().split()[0]
  for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
    try:
      return pd.to_datetime(date_str, format=fmt)
    except (ValueError, TypeError):
      continue
  return pd.to_datetime(date_str, dayfirst=True, errors="coerce")


@st.cache_data(ttl=30)
def load_and_process_google_sheet():
  df = pd.read_csv(CSV_URL)
  df.columns = df.columns.astype(str).str.strip()

  col_incident = next((c for c in df.columns if "Insiden" in c), "Tanggal Insiden")
  col_lappol = next(
      (c for c in df.columns if "Polisi" in c), "Tanggal Pelaporan Kepolisian"
  )

  col_submit_date_candidates = [
      c for c in df.columns if any(k in c.lower() for k in ["submit", "submission"])
  ]
  col_submit_date = (
      col_submit_date_candidates[0] if col_submit_date_candidates else None
  )

  df["_Insiden_Parsed"] = df[col_incident].apply(parse_mixed_date)
  df["_LapPol_Parsed"] = df[col_lappol].apply(parse_mixed_date)

  if col_submit_date:
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

  # A. Aging Incident & Status Berdasarkan Aging Incident
  df["Aging Incident (Hari)"] = (today - df["_Insiden_Valid"]).dt.days

  def get_insiden_status(aging):
    if pd.isna(aging):
      return "Belum Ada Insiden"
    elif aging < 30:
      return "Submit Asuransi Soon"
    elif 30 <= aging <= 45:
      return "Asuransi Diperjuangkan"
    else:
      return "Asuransi Expired"

  df["Status Aging Pelaporan"] = df["Aging Incident (Hari)"].apply(
      get_insiden_status
  )

  # B. Aging Pelaporan Polisi
  df["Aging Pelaporan (Hari)"] = (today - df["_LapPol_Valid"]).dt.days

  # C. Status & Aging Submission
  def get_submission_info(row):
    raw_sub_val = row[col_submit_date] if col_submit_date else None
    parsed_sub = row["_Submit_Parsed"]

    if pd.isna(raw_sub_val) or str(raw_sub_val).strip() == "" or str(raw_sub_val).strip().lower() == "nan":
      return "Belum Submit", np.nan
    
    if not pd.isna(parsed_sub) and parsed_sub > today:
      return "Salah Input Tanggal", np.nan
    
    if not pd.isna(parsed_sub):
      aging_sub = (today - parsed_sub).days
      return "Sudah Submit", max(0, aging_sub)
    else:
      return "Sudah Submit", 0

  sub_results = df.apply(get_submission_info, axis=1)
  df["Status Submission"] = [res[0] for res in sub_results]
  df["Aging Submission (Hari)"] = [res[1] for res in sub_results]

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
      options=df["Provinsi"].dropna().unique(),
      default=df["Provinsi"].dropna().unique(),
  )

  selected_status = st.sidebar.multiselect(
      "Pilih Status Aging Insiden",
      options=df["Status Aging Pelaporan"].unique(),
      default=df["Status Aging Pelaporan"].unique(),
  )

  df_filtered = df[
      (df["Provinsi"].isin(selected_prov))
      & (df["Status Aging Pelaporan"].isin(selected_status))
  ]

  # ---------------------------------------------------------
  # 4. Top Metric Scoreboard
  # ---------------------------------------------------------
  total_site = len(df_filtered)
  count_soon = len(
      df_filtered[df_filtered["Status Aging Pelaporan"] == "Submit Asuransi Soon"]
  )
  count_diperjuangkan = len(
      df_filtered[
          df_filtered["Status Aging Pelaporan"] == "Asuransi Diperjuangkan"
      ]
  )
  count_expired = len(
      df_filtered[df_filtered["Status Aging Pelaporan"] == "Asuransi Expired"]
  )

  count_sudah_submit = len(
      df_filtered[df_filtered["Status Submission"] == "Sudah Submit"]
  )
  count_reminder = len(
      df_filtered[df_filtered["Status Submission"] == "Belum Submit"]
  )

  m1, m2, m3, m4 = st.columns(4)
  m1.metric("Total Site Insiden", f"{total_site} Site")
  m2.metric("🟠 Submit Soon (<30 hr)", f"{count_soon} Site")
  m3.metric("🟡 Diperjuangkan (30-45 hr)", f"{count_diperjuangkan} Site")
  m4.metric("🔴 Expired (>=45 hr)", f"{count_expired} Site")

  s1, s2 = st.columns(2)
  s1.metric("✅ Sudah Submit Asuransi", f"{count_sudah_submit} Site")
  s2.metric("🔔 Reminding Harus Dikirim (Belum Submit)", f"{count_reminder} Site")

  st.markdown("---")

  # ---------------------------------------------------------
  # 5. Visualisasi Charts
  # ---------------------------------------------------------
  c1, c2 = st.columns(2)

  with c1:
    st.subheader("📊 Distribusi Status Aging Insiden")
    color_map = {
        "Submit Asuransi Soon": "#ff7f0e",
        "Asuransi Diperjuangkan": "#f1c40f",
        "Asuransi Expired": "#e74c3c",
        "Belum Ada Insiden": "#95a5a6",
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

  # ---------------------------------------------------------
  # 6. Tabel Detail dengan 2 Filter (Status Aging & Status Submission)
  # ---------------------------------------------------------
  st.subheader("📋 Detail Status & Aging Site (Form Original Columns)")

  col_f1, col_f2 = st.columns(2)
  with col_f1:
    unique_statuses = ["Semua"] + list(
        df_filtered["Status Aging Pelaporan"].unique()
    )
    table_status_filter = st.selectbox(
        "🔍 1. Filter Berdasarkan Status Aging Insiden", unique_statuses
    )

  with col_f2:
    unique_sub_statuses = ["Semua"] + list(
        df_filtered["Status Submission"].unique()
    )
    table_sub_filter = st.selectbox(
        "🔍 2. Filter Berdasarkan Status Submission", unique_sub_statuses
    )

  # Terapkan filter tabel
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
              if val == "Asuransi Expired"
              else (
                  "background-color: #fff9c4; color: #f57f17;"
                  if val == "Asuransi Diperjuangkan"
                  else (
                      "background-color: #ffe0b2; color: #e65100;"
                      if val == "Submit Asuransi Soon"
                      else (
                          "background-color: #ffebee; color: #c62828;"
                          if val in ["Belum Submit", "Salah Input Tanggal"]
                          else (
                              "background-color: #c8e6c9; color: #2e7d32;"
                              if val == "Sudah Submit"
                              else ""
                          )
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