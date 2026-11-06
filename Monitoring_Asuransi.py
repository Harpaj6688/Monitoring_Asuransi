from datetime import datetime
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import time

# ---------------------------------------------------------
# 0. Konfigurasi Halaman & Autentikasi Login
# ---------------------------------------------------------
st.set_page_config(
    page_title="MSS Insurance Claim & SLA Dashboard",
    page_icon="🛡️",
    layout="wide",
)

@st.dialog("⚠️ Sesi Berakhir (Idle Timeout)")
def session_expired_dialog():
    st.warning("Tidak ada aktivitas (idle) selama batas waktu yang ditentukan. Sesi Anda telah berakhir demi keamanan data.")
    st.markdown("Silakan klik tombol di bawah untuk kembali ke menu login.")
    if st.button("OK, Login Kembali", use_container_width=True):
        st.session_state["show_timeout_popup"] = False
        st.session_state["session_expired"] = False
        st.rerun()

def check_password():
    USERS = {
        "harry": "paswara123",
        "delda": "admin123",
        "siti": "sla_dashboard"
    }

    TIMEOUT_LIMIT = 600

    if "password_correct" in st.session_state and st.session_state["password_correct"]:
        if "last_active" in st.session_state:
            elapsed_time = time.time() - st.session_state["last_active"]
            if elapsed_time > TIMEOUT_LIMIT:
                st.session_state["show_timeout_popup"] = True
        
        st.markdown(
            f"""
            <meta http-equiv="refresh" content="{TIMEOUT_LIMIT + 1}">
            """,
            unsafe_allow_html=True
        )

    if st.session_state.get("show_timeout_popup", False):
        st.session_state["password_correct"] = False
        session_expired_dialog()
        return False

    if "password_correct" not in st.session_state or not st.session_state["password_correct"]:
        _, col_center, _ = st.columns([2.3, 1.4, 2.3])
        with col_center:
            st.markdown("<br><br>", unsafe_allow_html=True)
            with st.form("login_form", border=True):
                st.markdown("### 🔒 Login Dashboard")
                st.caption("Masukkan akun internal terdaftar.")
                username_input = st.text_input("Username")
                password_input = st.text_input("Password", type="password")
                submit_button = st.form_submit_button("Login", use_container_width=True)
                
                if submit_button:
                    if username_input in USERS and USERS[username_input] == password_input:
                        st.session_state["password_correct"] = True
                        st.session_state["logged_user"] = username_input
                        st.session_state["last_active"] = time.time()  
                        st.session_state["show_timeout_popup"] = False
                        st.rerun()
                    else:
                        st.error("😕 Username / Password salah!")
        return False
    else:
        st.session_state["last_active"] = time.time()
        return True

if not check_password():
    st.stop()

with st.sidebar:
    st.write(f"👤 Login sebagai: **{st.session_state['logged_user']}**")
    if st.button("🚪 Logout"):
        st.session_state["password_correct"] = False
        st.session_state["show_timeout_popup"] = False
        st.rerun()

# ---------------------------------------------------------
# 1. Konfigurasi Utama Dashboard
# ---------------------------------------------------------
st.title("🛡️ MSS Insurance Claim & SLA Tracking Dashboard")
st.caption("Live Connection Google Sheets (Google Form) & Otomatisasi SLA")

SHEET_ID = "15jMIWecycZgWFJ4zWMRNp8FCT5umgqdok_hF2ByHTeQ"
GID = "1414464208"
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={GID}"


# ---------------------------------------------------------
# 2. Function Parsing Tanggal Super Agresif
# ---------------------------------------------------------
def parse_mixed_date(date_val):
  if pd.isna(date_val) or str(date_val).strip() == "" or str(date_val).strip().lower() in ["nan", "none", "-", "nat"]:
    return pd.NaT
  
  date_str = str(date_val).strip().split()[0]

  month_map = {
      '-jan-': '-01-', '-feb-': '-02-', '-mar-': '-03-', '-apr-': '-04-', '-mei-': '-05-', '-jun-': '-06-',
      '-jul-': '-07-', '-agu-': '-08-', '-agt-': '-08-', '-sep-': '-09-', '-okt-': '-10-', '-oct-': '-10-',
      '-nov-': '-11-', '-des-': '-12-', '-dec-': '-12-'
  }
  
  lower_str = date_str.lower()
  for k, v in month_map.items():
    if k in lower_str:
      lower_str = lower_str.replace(k, v)
      break

  for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%y", "%d/%m/%y", "%d-%b-%Y", "%d %b %Y"):
    try:
      parsed = pd.to_datetime(lower_str, format=fmt, errors='coerce')
      if not pd.isna(parsed):
        return parsed
    except:
      continue

  try:
    parsed = pd.to_datetime(date_str, errors='coerce', dayfirst=True)
    if not pd.isna(parsed):
      return parsed
  except:
    pass

  return pd.NaT


@st.cache_data(ttl=30)
def load_and_process_google_sheet():
  df = pd.read_csv(CSV_URL)
  df.columns = df.columns.astype(str).str.strip()

  # MENGGUNAKAN NAMA KOLOM EXACT SESUAI REQUEST LO:
  col_incident = "Tanggal Insiden"
  col_lappol = "Tanggal Pelaporan Kepolisian"

  # Cari kolom submission secara fleksibel
  submit_candidates = [c for c in df.columns if any(k in c.lower() for k in ["submit", "submission"])]
  col_submit_date = submit_candidates[0] if submit_candidates else None

  # Eksekusi parsing tanggal
  df["_Insiden_Parsed"] = df[col_incident].apply(parse_mixed_date) if col_incident in df.columns else pd.NaT
  df["_LapPol_Parsed"] = df[col_lappol].apply(parse_mixed_date) if col_lappol in df.columns else pd.NaT
  df["_Submit_Parsed"] = df[col_submit_date].apply(parse_mixed_date) if (col_submit_date and col_submit_date in df.columns) else pd.NaT

  today = pd.Timestamp(datetime.now().date())

  # 1. Aging Tanggal Incident (Hari) sampai Hari Ini
  df["Aging Incident (Hari)"] = (today - df["_Insiden_Parsed"].dt.normalize()).dt.days
  df["Aging Incident (Hari)"] = df["Aging Incident (Hari)"].apply(lambda x: x if pd.notna(x) and x >= 0 else np.nan)

  # 2. Aging Tanggal Pelaporan (Hari) sampai Hari Ini
  df["Aging Pelaporan (Hari)"] = (today - df["_LapPol_Parsed"].dt.normalize()).dt.days
  df["Aging Pelaporan (Hari)"] = df["Aging Pelaporan (Hari)"].apply(lambda x: x if pd.notna(x) and x >= 0 else np.nan)

  # 3. Aging Tanggal Submission (Hari) sampai Hari Ini
  df["Aging Submission (Hari)"] = (today - df["_Submit_Parsed"].dt.normalize()).dt.days if (col_submit_date and col_submit_date in df.columns) else np.nan
  df["Aging Submission (Hari)"] = df["Aging Submission (Hari)"].apply(lambda x: x if pd.notna(x) and x >= 0 else np.nan)

  # Column Possible Reject berdasarkan Aging Incident > 30 Hari
  df["Possible Reject"] = df["Aging Incident (Hari)"].apply(lambda x: "Possible Reject (>30 Hari)" if pd.notna(x) and x > 30 else "Aman (≤30 Hari)")

  # Status submission
  def get_submission_status(row):
    raw_sub_val = row[col_submit_date] if (col_submit_date and col_submit_date in df.columns) else None
    parsed_sub = row["_Submit_Parsed"]

    if pd.isna(raw_sub_val) or str(raw_sub_val).strip() == "" or str(raw_sub_val).strip().lower() in ["nan", "none", "-"]:
      return "Belum Submit"
    if not pd.isna(parsed_sub) and parsed_sub > today:
      return "Salah Input Tanggal"
    return "Sudah Submit"

  df["Status Submission"] = df.apply(get_submission_status, axis=1)

  # Scoreboard Status
  def get_scoreboard_status(row):
    aging = row["Aging Incident (Hari)"]

    if pd.notna(aging) and aging > 30:
      return "Possible Reject"
    
    sub_stat = row["Status Submission"]
    if sub_stat == "Sudah Submit":
      return "Sudah Submit Asuransi"
    
    if pd.isna(aging):
      return "Reminding Harus Dikirim (Belum Submit)"
    
    if aging > 14:
      return "Warning (Submit Soon)"
    else:
      return "Prepare submit"

  df["Status Aging Pelaporan"] = df.apply(get_scoreboard_status, axis=1)

  # Parsing Nilai BOQ untuk kalkulasi nominal
  boq_price_cols = [
      c for c in df.columns 
      if any(k in c.lower() for k in ["boq", "harga", "cost", "nilai", "amount", "total"])
      and not any(exc in c.lower() for exc in ["upload", "link", "url"])
  ]
  col_price = boq_price_cols[0] if boq_price_cols else None
  
  if col_price:
    cleaned_price = (
        df[col_price].astype(str)
        .str.replace('Rp', '', case=False, regex=False)
        .str.replace('.', '', regex=False)
        .str.replace(',', '.', regex=False)
        .str.strip()
    )
    df["_Parsed_BOQ_Value"] = pd.to_numeric(cleaned_price, errors='coerce').fillna(0)
  else:
    df["_Parsed_BOQ_Value"] = 0.0

  return df, today, col_incident, col_lappol


try:
  df, today_date, det_inc, det_lap = load_and_process_google_sheet()

  # ---------------------------------------------------------
  # 3. Sidebar Filter Utama
  # ---------------------------------------------------------
  st.sidebar.header("🔍 Filter Dashboard")
  st.sidebar.info(f"📅 **Tanggal System:**\n{today_date.strftime('%d %B %Y')}")
  st.sidebar.caption(f"📌 **Kolom Terhubung:**\n- Insiden: `{det_inc}`\n- LapPol: `{det_lap}`")

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
  count_sudah_submit = len(df_filtered[df_filtered["Status Submission"] == "Sudah Submit"])
  
  df_belum_submit = df_filtered[(df_filtered["Status Submission"] == "Belum Submit") & ((df_filtered["Aging Incident (Hari)"].isna()) | (df_filtered["Aging Incident (Hari)"] <= 30))]
  count_belum_submit = len(df_belum_submit)
  
  # Possible Reject (>30 hari incident, terlepas sudah / belum submit)
  count_possible_reject = len(df_filtered[df_filtered["Aging Incident (Hari)"] > 30])

  m1, m2, m3, m4 = st.columns(4)
  
  with m1:
    st.metric(label="Total Incident", value=f"{total_site} Site")
    
  with m2:
    st.metric(label="Sudah Submit", value=f"{count_sudah_submit} Site")
    
  with m3:
    st.metric(label="Belum Submit", value=f"{count_belum_submit} Site")
    aging_list = df_belum_submit["Aging Incident (Hari)"].dropna().tolist()
    aging_str = ", ".join([f"{int(a)}h" for a in aging_list]) if aging_list else "0h"
    st.caption(f"⚠️ Aging: {aging_str}")
    
  with m4:
    st.metric(
        label="Possible Reject", 
        value=f"{count_possible_reject} Site", 
        delta=">30 Hari Incident", 
        delta_color="inverse"
    )

  st.markdown("---")

  # ---------------------------------------------------------
  # 5. Analisis Material Kehilangan & Top 10 BOQ Termahal
  # ---------------------------------------------------------
  st.subheader("🛠️ Analisis Material Kehilangan & Nilai BOQ Termahal")

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
          title="Top 5 Material Kehilangan Terbanyak",
          text='Jumlah',
          color='Jumlah',
          color_continuous_scale='Blues'
      )
      st.plotly_chart(fig_mat, use_container_width=True)
    else:
      st.info("Kolom kategori Material Kehilangan spesifik belum terdeteksi pada form Google Sheet.")

  with mc2:
    if col_mat and col_price:
      st.markdown(f"##### Tabel: Top 10 Material BOQ Termahal ({col_price})")
      df_boq = df_filtered.copy()
      
      boq_summary = df_boq.groupby(col_mat)['_Parsed_BOQ_Value'].sum().reset_index()
      boq_summary.columns = ['Material', 'Total Nilai BOQ']
      top10_boq = boq_summary.sort_values(by='Total Nilai BOQ', ascending=False).head(10).reset_index(drop=True)
      
      st.dataframe(top10_boq.style.format({'Total Nilai BOQ': 'Rp {:,.2f}'}), use_container_width=True, height=380)

      total_boq_value = df_boq['_Parsed_BOQ_Value'].sum()
      st.metric(
          label="💰 Total Keseluruhan Nilai Claim BOQ", 
          value=f"Rp {total_boq_value:,.2f}"
      )
    else:
      st.info("Kolom Nilai/Harga BOQ belum terdeteksi secara otomatis.")

  # ---------------------------------------------------------
  # 6. Valuasi BOQ (Tepat di Bawah Top Material BOQ)
  # ---------------------------------------------------------
  st.markdown("---")
  st.markdown("#### 💰 Valuasi BOQ Overview (Sedang Berjalan vs Possible Reject)")

  boq_possible_reject_val = df_filtered[df_filtered["Aging Incident (Hari)"] > 30]['_Parsed_BOQ_Value'].sum()
  boq_sedang_berjalan_val = df_filtered[(df_filtered["Aging Incident (Hari)"].isna()) | (df_filtered["Aging Incident (Hari)"] <= 30)]['_Parsed_BOQ_Value'].sum()

  b_col1, b_col2 = st.columns(2)

  with b_col1:
    st.markdown(
        f"""
        <div style="padding: 16px; border-radius: 8px; background-color: #f0fdf4; border: 1px solid #bbf7d0; border-left: 5px solid #16a34a;">
            <p style="margin: 0; font-size: 13px; color: #15803d; font-weight: 600;">VALUASI BOQ SEDANG BERJALAN</p>
            <h3 style="margin: 6px 0 2px 0; color: #166534; font-size: 22px;">Rp {boq_sedang_berjalan_val:,.2f}</h3>
            <p style="margin: 0; font-size: 11px; color: #4b5563;">Status aman / Incident ≤ 30 Hari</p>
        </div>
        """, 
        unsafe_allow_html=True
    )

  with b_col2:
    st.markdown(
        f"""
        <div style="padding: 16px; border-radius: 8px; background-color: #fef2f2; border: 1px solid #fecaca; border-left: 5px solid #dc2626;">
            <p style="margin: 0; font-size: 13px; color: #b91c1c; font-weight: 600;">VALUASI BOQ POSSIBLE REJECT</p>
            <h3 style="margin: 6px 0 2px 0; color: #991b1b; font-size: 22px;">Rp {boq_possible_reject_val:,.2f}</h3>
            <p style="margin: 0; font-size: 11px; color: #4b5563;">Potensi reject asuransi / Incident > 30 Hari</p>
        </div>
        """, 
        unsafe_allow_html=True
    )

  # ---------------------------------------------------------
  # 7. Tabel Detail dengan 2 Filter
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
          "Possible Reject"
      ]
  ]

  added_cols = [
      "Aging Incident (Hari)",
      "Aging Pelaporan (Hari)",
      "Status Aging Pelaporan",
      "Status Submission",
      "Aging Submission (Hari)",
      "Possible Reject"
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
              if val in ["Expired", "Possible Reject", "Possible Reject (>30 Hari)"]
              else (
                  "background-color: #fff9c4; color: #f57f17;"
                  if val == "Warning (Submit Soon)"
                  else (
                      "background-color: #c8e6c9; color: #2e7d32;"
                      if val in ["Prepare submit", "Sudah Submit Asuransi", "Aman (≤30 Hari)"]
                      else (
                          "box-shadow: none; background-color: #ffebee; color: #c62828;"
                          if val in ["Belum Submit", "Salah Input Tanggal"]
                          else ""
                      )
                  )
              )
          ),
          subset=["Status Aging Pelaporan", "Status Submission", "Possible Reject"],
      ),
      use_container_width=True,
      height=500,
  )

except Exception as e:
  st.error("Terjadi kendala pada script dashboard:")
  st.exception(e)