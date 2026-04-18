import streamlit as st
import requests
import re
from datetime import datetime, timezone
import os # New tool to safely check for files

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
        # Note: If your file on GitHub is NOAA.png, change the name below!
        if os.path.exists("NOAA.png"):
            st.image("noaa.png", width=75)
        else:
            st.caption("[NOAA Logo Missing]")
    with logo2:
        # Note: If your file on GitHub is NWS.png, change the name below!
        if os.path.exists("NWS.png"):
            st.image("nws.png", width=75)
        else:
            st.caption("[NWS Logo Missing]")

st.divider()

# --- FUNCTIONS ---

def get_5min_asos():
    """Pulls the high-frequency 5-minute ASOS data and formats it if the raw string is missing."""
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
                    
                    temp = props.get('temperature', {}).get('value')
                    dew = props.get('dewpoint', {}).get('value')
                    temp_str = f"{int(temp)}" if temp is not None else "M"
                    dew_str = f"{int(dew)}" if dew is not None else "M"
                    
                    pres_pa = props.get('barometricPressure', {}).get('value')
                    pres_inhg = round(pres_pa / 3386.389, 2) if pres_pa is not None else "M"
                    
                    raw = f"BHM 5-MIN ({time_str}) | Wind: {wind_str} | Vis: {vis_sm}SM | Temp/Dew: {temp_str}/{dew_str}°C | Alt: {pres_inhg} inHg"
                    
                if timestamp:
                    return raw, timestamp, None
            return None, None, "No data features found in NWS ping."
        else:
            return None, None, f"HTTP {response.status_code}"
    except Exception as e:
        return None, None, f"Error: {str(e)}"

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
latest_raw, latest_ts, diag_err = get_5min_asos()

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

# --- MIDDLE UI: SPECI CALCULATORS ---
st.subheader("JO 7900.5F SPECI Calculators")

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 🌫️ Visibility Changes")
    old_vis = st.number_input("Previous Visibility (SM)", min_value=0.0, value=10.0, step=0.25)
    new_vis = st.number_input("Current Visibility (SM)", min_value=0.0, value=float(live_vis), step=0.25)
    
    vis_speci, vis_trigger = check_speci(old_vis, new_vis, vis_thresholds)
    
    if old_vis != new_vis:
        if vis_speci:
            st.error(f"🚨 **SPECI REQUIRED:** Visibility crossed the {vis_trigger} SM threshold.")
        else:
            st.success("✅ No SPECI required for visibility change.")

with col2:
    st.markdown("### ☁️ Ceiling Changes")
    old_cig = st.number_input("Previous Ceiling (Feet)", min_value=0, value=5000, step=100)
    new_cig = st.number_input("Current Ceiling (Feet)", min_value=0, value=int(live_cig), step=100)
    
    cig_speci, cig_trigger = check_speci(old_cig, new_cig, cig_thresholds)
    
    if old_cig != new_cig:
        if cig_speci:
            st.error(f"🚨 **SPECI REQUIRED:** Ceiling crossed the {cig_trigger} FT threshold.")
        else:
            st.success("✅ No SPECI required for ceiling change.")

st.divider()

# --- BOTTOM UI: REMARKS (RMK) BUILDER ---
st.subheader("📝 Remarks (RMK) Builder")
st.markdown("Select current events to generate a correctly formatted JO 7900.5F RMK string.")

rmk_col1, rmk_col2, rmk_col3 = st.columns(3)

with rmk_col1:
    st.markdown("**🌪️ Pressure Trend**")
    pressure_rmk = st.radio("Select Pressure Event:", 
                            ["None", "Rising Rapidly (PRESRR)", "Falling Rapidly (PRESFR)"], 
                            index=0)

with rmk_col2:
    st.markdown("**⚡ Lightning**")
    has_ltg = st.checkbox("Lightning Observed")
    if has_ltg:
        ltg_freq = st.selectbox("Frequency:", ["OCNL (1-6/min)", "FRQ (7-12/min)", "CONS (>12/min)"])
        ltg_loc = st.selectbox("Location (LTG):", 
                               ["ALQDS", "OHD", "VC", "DSNT", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])

with rmk_col3:
    st.markdown("**🌩️ Thunderstorm Tracking**")
    has_ts = st.checkbox("Thunderstorm (TS) Active")
    if has_ts:
        ts_loc = st.selectbox("Location (TS):", 
                              ["OHD", "VC", "DSNT", "ALQDS", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])
        ts_mov = st.selectbox("Moving Toward:", 
                              ["Unknown", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])

st.markdown("---")
rmk_col4, rmk_col5 = st.columns(2)

with rmk_col4:
    st.markdown("**💨 Peak Wind**")
    has_pk_wnd = st.checkbox("Peak Wind (>25kt)")
    if has_pk_wnd:
        pk_dir = st.number_input("Direction (Degrees)", min_value=0, max_value=360, step=10, value=270)
        pk_spd = st.number_input("Speed (Knots)", min_value=26, max_value=200, step=1, value=35)
        pk_time = st.number_input("Time (Minutes past hour)", min_value=0, max_value=59, step=1, value=15)

rmk_parts = []
if has_pk_wnd: 
    rmk_parts.append(f"PK WND {pk_dir:03d}{pk_spd}/{pk_time:02d}")
if has_ts:
    ts_str = f"TS {ts_loc}"
    if ts_mov != "Unknown": 
        ts_str += f" MOV {ts_mov}"
    rmk_parts.append(ts_str)
if has_ltg: 
    rmk_parts.append(f"LTG {ltg_freq.split(' ')[0]} {ltg_loc}")
if pressure_rmk == "Rising Rapidly (PRESRR)": 
    rmk_parts.append("PRESRR")
elif pressure_rmk == "Falling Rapidly (PRESFR)": 
    rmk_parts.append("PRESFR")

if rmk_parts:
    st.success("**Generated Remark String:**")
    st.code("RMK " + " ".join(rmk_parts), language="markdown")
else:
    st.info("Select weather events above to build your remarks string.")