import streamlit as st
import requests
import re
from datetime import datetime, timezone
import os

# --- PAGE SETUP ---
st.set_page_config(page_title="BHM CWO Dashboard", layout="wide")

# --- HEADER WITH LOGOS ---
header_col1, header_col2 = st.columns([5, 1])

with header_col1:
    st.title("BHM CWO Tactical Dashboard 🌪️")
    st.subheader("JO 7900.5F Logic Engine & Live Interface")

with header_col2:
    st.markdown("<br>", unsafe_allow_html=True)
    logo1, logo2 = st.columns(2)
    with logo1:
        if os.path.exists("noaa.png"):
            st.image("noaa.png", width=75)
        else:
            st.caption("[NOAA Logo]")
    with logo2:
        if os.path.exists("nws.png"):
            st.image("nws.png", width=75)
        else:
            st.caption("[NWS Logo]")

st.divider()

# --- FUNCTIONS ---

def get_5min_asos():
    """Pulls high-frequency 5-minute ASOS data and extracts Temp/Dew for calculations."""
    try:
        url = "https://api.weather.gov/stations/KBHM/observations?limit=3"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            "Accept": "application/geo+json"
        }
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            features = response.json().get('features', [])
            if len(features) > 0:
                ob = features[0]
                props = ob['properties']
                timestamp = props.get('timestamp')
                raw = props.get('rawMessage')
                
                # Extract Temp and Dewpoint (Celsius) for Cloud Base Calculator
                try:
                    temp_c = float(props.get('temperature', {}).get('value'))
                    dew_c = float(props.get('dewpoint', {}).get('value'))
                except (TypeError, ValueError):
                    temp_c, dew_c = None, None
                
                if not raw and timestamp:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    time_str = dt.strftime("%H:%MZ")
                    
                    wdir = props.get('windDirection', {}).get('value')
                    wspd_kmh = props.get('windSpeed', {}).get('value')
                    wdir_str = f"{int(wdir):03d}" if wdir is not None else "VRB"
                    wspd_kts = int(round(wspd_kmh / 1.852)) if wspd_kmh is not None else 0
                    wind_str = f"{wdir_str}@{wspd_kts}kt"
                    
                    vis_m = props.get('visibility', {}).get('value')
                    vis_sm = round(vis_m / 1609.34, 1) if vis_m is not None else "M"
                    
                    temp_str = f"{int(temp_c)}" if temp_c is not None else "M"
                    dew_str = f"{int(dew_c)}" if dew_c is not None else "M"
                    
                    pres_pa = props.get('barometricPressure', {}).get('value')
                    pres_inhg = round(pres_pa / 3386.389, 2) if pres_pa is not None else "M"
                    
                    raw = f"BHM 5-MIN ({time_str}) | Wind: {wind_str} | Vis: {vis_sm}SM | Temp/Dew: {temp_str}/{dew_str}°C | Alt: {pres_inhg} inHg"
                    
                if timestamp:
                    return raw, timestamp, temp_c, dew_c, None
            return None, None, None, None, "No data features found in NWS ping."
        else:
            return None, None, None, None, f"HTTP {response.status_code}"
    except Exception as e:
        return None, None, None, None, f"Error: {str(e)}"

def get_awc_data():
    """Fetches the hourly METARs from the reliable AWC API."""
    try:
        url = "https://aviationweather.gov/api/data/metar?ids=KBHM&format=json&hours=6"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def extract_vis_and_cig(metar_string):
    """Parses raw METAR string to find Visibility and Ceiling."""
    vis_val = 10.0
    cig_val = 10000 
    if "Error" in metar_string or "No recent" in metar_string or not metar_string:
        return vis_val, cig_val

    vis_match = re.search(r'\s(M?P?\d+/?\d*\s?\d*/?\d*)SM', metar_string)
    if vis_match:
        vis_str = vis_match.group(1).replace('P', '').replace('M', '').strip()
        try:
            if " " in vis_str:
                whole, frac = vis_str.split(" ")
                num, den = frac.split("/")
                vis_val = float(whole) + (float(num) / float(den))
            elif "/" in vis_str:
                num, den = vis_str.split("/")
                vis_val = float(num) / float(den)
            else:
                vis_val = float(vis_str)
        except:
            pass 

    cig_match = re.search(r'(BKN|OVC|VV)(\d{3})', metar_string)
    if cig_match:
        cig_val = int(cig_match.group(2)) * 100

    return vis_val, cig_val

def check_speci(old_val, new_val, thresholds):
    """Checks if a value crossed any JO 7900.5F threshold."""
    for t in thresholds:
        if (old_val >= t and new_val < t) or (old_val < t and new_val >= t):
            return True, t
    return False, None

vis_thresholds = [3.0, 2.0, 1.0, 0.5, 0.25]
cig_thresholds = [3000, 1500, 1000, 500, 200]

# --- COMM CHECK UI (5-Minute Early Warning) ---
st.markdown("### 📡 System Comm Status (5-Min Early Warning)")
latest_raw, latest_ts, live_temp_c, live_dew_c, diag_err = get_5min_asos()

if latest_raw and latest_ts:
    try:
        ob_time = datetime.fromisoformat(latest_ts.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        age_minutes = (now - ob_time).total_seconds() / 60

        col_a, col_b = st.columns([2, 1])
        with col_a:
            st.code(f"ASOS 5-MIN PING: {latest_raw}", language="bash")
        with col_b:
            if age_minutes > 20:
                st.error(f"🚨 **COMM WARNING:** Last ASOS ping is **{int(age_minutes)} minutes old!** Check long-line.")
            else:
                st.success(f"✅ **Comms Good:** Latency is **{int(age_minutes)}** mins.")
    except Exception as e:
        st.warning("Could not calculate age.")
else:
    st.warning(f"⚠️ 5-minute network ping unavailable. Diagnostic code: {diag_err}")

st.divider()

# --- PREPARE THE HOURLY METAR LIST ---
awc_data = get_awc_data()
if awc_data:
    recent_metars = [obs.get('rawOb', 'No raw string') for obs in awc_data[:6]]
else:
    recent_metars = ["No recent METARs found."]

latest_metar = recent_metars[0] if len(recent_metars) > 0 else ""
live_vis, live_cig = extract_vis_and_cig(latest_metar)

# --- TOP UI: OBSERVATIONS & RADAR ---
top_col1, top_col2 = st.columns([1, 1])

with top_col1:
    st.markdown("#### 📝 Last 6 Transmitted METARs")
    if "No recent" not in latest_metar:
        for i, metar in enumerate(recent_metars):
            if i == 0:
                st.error(f"**LATEST:** `{metar}`")
            elif i == 1:
                st.warning(f"`{metar}`")
            else:
                st.info(f"`{metar}`")
    else:
        st.warning("Could not load AWC METARs.")

with top_col2:
    st.markdown("#### 📡 Live Radar (KBMX)")
    st.image("https://radar.weather.gov/ridge/standard/KBMX_loop.gif", caption="Live NWS Birmingham (BMX) Radar Loop", use_container_width=True)

st.divider()

# --- MIDDLE UI: SPECI & CLOUD CALCULATORS ---
st.subheader("🧮 JO 7900.5F Calculators")

calc_col1, calc_col2, calc_col3 = st.columns(3)

with calc_col1:
    st.markdown("**🌫️ Visibility SPECI**")
    old_vis = st.number_input("Previous Visibility (SM)", min_value=0.0, value=10.0, step=0.25)
    new_vis = st.number_input("Current Visibility (SM)", min_value=0.0, value=float(live_vis), step=0.25)
    vis_speci, vis_trigger = check_speci(old_vis, new_vis, vis_thresholds)
    if old_vis != new_vis:
        if vis_speci: st.error(f"🚨 **SPECI REQUIRED:** Crossed {vis_trigger} SM.")
        else: st.success("✅ No SPECI required.")

with calc_col2:
    st.markdown("**☁️ Ceiling SPECI**")
    old_cig = st.number_input("Previous Ceiling (Feet)", min_value=0, value=5000, step=100)
    new_cig = st.number_input("Current Ceiling (Feet)", min_value=0, value=int(live_cig), step=100)
    cig_speci, cig_trigger = check_speci(old_cig, new_cig, cig_thresholds)
    if old_cig != new_cig:
        if cig_speci: st.error(f"🚨 **SPECI REQUIRED:** Crossed {cig_trigger} FT.")
        else: st.success("✅ No SPECI required.")

with calc_col3:
    st.markdown("**☁️ Convective Cloud Base**")
    st.caption("Based on 5-Min ASOS Temp/Dew Spread")
    
    if live_temp_c is not None and live_dew_c is not None:
        # Convert C to F
        t_f = (live_temp_c * 9/5) + 32
        d_f = (live_dew_c * 9/5) + 32
        spread_f = t_f - d_f
        
        # Exact math from the BHM Cheat Sheet: 10 spread = 2300 AGL
        ccl_agl = int(spread_f * 230)
        
        st.info(f"**Live Spread:** {int(spread_f)}°F")
        st.success(f"**Suggested Base:** {ccl_agl} ft AGL")
    else:
        st.warning("Awaiting live Temp/Dew data...")

st.divider()

# --- BOTTOM UI: REMARKS (RMK) BUILDER ---
st.subheader("📝 Remarks (RMK) Builder")
st.markdown("Constructs remarks based on the strict BHM METAR Order of Remarks checklist.")

rmk_col1, rmk_col2, rmk_col3, rmk_col4 = st.columns(4)

with rmk_col1:
    st.markdown("**💨 Peak Wind**")
    has_pk_wnd = st.checkbox("Peak Wind (>25kt)")
    if has_pk_wnd:
        pk_dir = st.number_input("Direction (Deg)", min_value=0, max_value=360, step=10, value=270)
        pk_spd = st.number_input("Speed (Kts)", min_value=26, max_value=200, step=1, value=35)
        pk_time = st.number_input("Time (Min)", min_value=0, max_value=59, step=1, value=15)

with rmk_col2:
    st.markdown("**⚡ Lightning**")
    has_ltg = st.checkbox("Lightning Observed")
    if has_ltg:
        ltg_freq = st.selectbox("Frequency:", ["OCNL", "FRQ", "CONS"])
        ltg_types = st.multiselect("Type:", ["IC", "CG", "CC", "CA"], default=["CG"])
        ltg_loc = st.selectbox("Location (LTG):", ["ALQDS", "OHD", "VC", "DSNT", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])

with rmk_col3:
    st.markdown("**🌩️ Thunderstorm**")
    has_ts = st.checkbox("Thunderstorm Active")
    if has_ts:
        ts_loc = st.selectbox("Location (TS):", ["OHD", "VC", "DSNT", "ALQDS", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])
        ts_mov = st.selectbox("Moving:", ["Unknown", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])

with rmk_col4:
    st.markdown("**🌧️ Other Elements**")
    has_virga = st.checkbox("VIRGA")
    if has_virga:
        virga_loc = st.selectbox("Direction:", ["ALQDS", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])
        
    pressure_rmk = st.radio("Pressure:", ["None", "Rising Rapidly", "Falling Rapidly"])

# Display observer reminders if TS is checked
if has_ts:
    st.warning("""
    **🚨 THUNDERSTORM OBSERVER REMINDERS:**
    * 🌩️ **Present WX:** Make sure to enter `TS`!
    * ☁️ **Sky Condition:** Append `CB` to the appropriate cloud layer!
    * 📡 **ALDARS Override:** Change ALDARS to `MAN` (Turn off `SEQ`) if the TS is on-station to prevent ASOS from auto-appending `TS DSNT`.
    """)

# STRICT ORDER APPLIES HERE (Based on BHM Reference Card)
rmk_parts = []

# C) PK WND
if has_pk_wnd: 
    rmk_parts.append(f"PK WND {pk_dir:03d}{pk_spd}/{pk_time:02d}")

# H) LTG
if has_ltg: 
    type_str = "".join(ltg_types)
    rmk_parts.append(f"{ltg_freq} LTG{type_str} {ltg_loc}")

# K) TS / TS LOCATION
if has_ts:
    ts_str = f"TS {ts_loc}"
    if ts_mov != "Unknown": 
        ts_str += f" MOV {ts_mov}"
    rmk_parts.append(ts_str)

# M) VIRGA
if has_virga:
    if virga_loc == "ALQDS": rmk_parts.append("VIRGA ALQDS")
    else: rmk_parts.append(f"VIRGA {virga_loc}")

# R) PRESRR/PRESFR
if pressure_rmk == "Rising Rapidly": 
    rmk_parts.append("PRESRR")
elif pressure_rmk == "Falling Rapidly": 
    rmk_parts.append("PRESFR")

st.markdown("---")
if rmk_parts:
    st.success("**Generated Remark String:**")
    st.code("RMK " + " ".join(rmk_parts), language="markdown")
else:
    st.info("Select weather events above to build your remarks string.")