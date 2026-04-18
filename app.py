import streamlit as st
import requests
import re
from datetime import datetime, timezone, timedelta
import os
import PyPDF2

# --- PAGE SETUP ---
st.set_page_config(page_title="BHM CWO Dashboard", layout="wide")

# --- HEADER WITH LOGOS ---
header_col1, header_col2 = st.columns([4, 2])

with header_col1:
    st.title("BHM CWO Tactical Dashboard 🌪️")
    st.subheader("JO 7900.5E Logic Engine & Live Interface")

with header_col2:
    st.markdown("<br>", unsafe_allow_html=True)
    logo1, logo2 = st.columns(2)
    with logo1:
        if os.path.exists("Cat and Hat.jpg"):
            st.image("Cat and Hat.jpg", width=250)
            st.caption("**Created by Eric Hattendorf**")
        else:
            st.caption("[Cat & Hat Missing]")
    with logo2:
        if os.path.exists("NWS.png"):
            st.image("NWS.png", width=100)
        else:
            st.caption("[NWS Logo]")

st.divider()

# --- FUNCTIONS ---

NWS_HEADERS = {
    "User-Agent": "BHM_CWO_Dashboard/2.0 (local_tactical_display)",
    "Accept": "application/geo+json"
}

def parse_nws_properties(props):
    """Helper function to turn NWS raw variables into a readable string."""
    timestamp = props.get('timestamp')
    if not timestamp: return None, None, None, None
    
    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    time_str = dt.strftime("%H:%MZ")
    
    try:
        temp_c = float(props.get('temperature', {}).get('value'))
        dew_c = float(props.get('dewpoint', {}).get('value'))
    except (TypeError, ValueError):
        temp_c, dew_c = None, None

    wdir = props.get('windDirection', {}).get('value')
    wspd_kmh = props.get('windSpeed', {}).get('value')
    wdir_str = f"{int(wdir):03d}" if wdir is not None else "VRB"
    wspd_kts = int(round(wspd_kmh / 1.852)) if wspd_kmh is not None else 0
    wind_str = f"{wdir_str}@{wspd_kts}kt"
    
    vis_m = props.get('visibility', {}).get('value')
    vis_sm = round(vis_m / 1609.34, 1) if vis_m is not None else "M"
    
    # --- FIXED CLOUD LAYER PARSING ---
    clouds_str = ""
    cloud_layers = props.get('cloudLayers') or []
    if cloud_layers:
        layer_strs = []
        for layer in cloud_layers:
            amt = layer.get('amount', '---')
            base_dict = layer.get('base')
            base_m = base_dict.get('value') if isinstance(base_dict, dict) else None
            
            if base_m is not None and amt not in ["CLR", "SKC"]:
                base_ft = base_m * 3.28084
                base_hnds = int(round(base_ft / 100))
                layer_strs.append(f"{amt}{base_hnds:03d}")
            else:
                layer_strs.append(amt)
        clouds_str = " ".join(layer_strs)
        
    if not clouds_str:
        desc = props.get('textDescription', '')
        if desc and "Clear" in desc: 
            clouds_str = "CLR"
        else: 
            clouds_str = "M"
            
    temp_str = f"{int(temp_c)}" if temp_c is not None else "M"
    dew_str = f"{int(dew_c)}" if dew_c is not None else "M"
    
    pres_pa = props.get('barometricPressure', {}).get('value')
    pres_inhg = round(pres_pa / 3386.389, 2) if pres_pa is not None else "M"
    
    formatted_str = f"({time_str}) | Wind: {wind_str} | Vis: {vis_sm}SM | Sky: {clouds_str} | Temp/Dew: {temp_str}/{dew_str}°C | Alt: {pres_inhg} inHg"
    return formatted_str, timestamp, temp_c, dew_c

def get_5min_asos():
    """Pulls high-frequency 5-minute ASOS data using an NWS-compliant method."""
    try:
        url = "https://api.weather.gov/stations/KBHM/observations?limit=10"
        response = requests.get(url, headers=NWS_HEADERS, timeout=5)
        
        if response.status_code == 200:
            features = response.json().get('features', [])
            if len(features) > 0:
                ob = features[0]
                props = ob['properties']
                raw = props.get('rawMessage')
                formatted_str, timestamp, temp_c, dew_c = parse_nws_properties(props)
                
                if formatted_str:
                    if raw:
                        final_raw = f"BHM 5-MIN ({timestamp[11:16]}Z) | {raw}"
                    else:
                        final_raw = f"BHM 5-MIN {formatted_str}"
                    return final_raw, timestamp, temp_c, dew_c, None
                    
            return None, None, None, None, "No data features found in NWS ping."
        else:
            return None, None, None, None, f"HTTP {response.status_code}"
    except Exception as e:
        return None, None, None, None, f"Error: {str(e)}"

def get_regional_5min():
    """Pulls the 5-min data for regional stations and formats it beautifully."""
    stations = ["KTCL", "KANB", "KEET", "KPLR"]
    data = {}
    
    for stn in stations:
        try:
            url = f"https://api.weather.gov/stations/{stn}/observations?limit=6"
            res = requests.get(url, headers=NWS_HEADERS, timeout=5)
            
            if res.status_code == 200:
                features = res.json().get('features', [])
                parsed = []
                for ob in features:
                    props = ob['properties']
                    raw = props.get('rawMessage')
                    formatted_str, ts, _, _ = parse_nws_properties(props)
                    
                    if formatted_str:
                        if raw:
                            parsed.append(f"({ts[11:16]}Z) | {raw}")
                        else:
                            parsed.append(formatted_str)
                data[stn] = parsed
            else:
                data[stn] = [f"API Error: HTTP {res.status_code}"]
        except Exception as e:
            data[stn] = ["Connection Error"]
    return data

def get_awc_data():
    try:
        url = "https://aviationweather.gov/api/data/metar?ids=KBHM&format=json&hours=6"
        response = requests.get(url, timeout=5)
        if response.status_code == 200: return response.json()
        return None
    except: return None

def extract_vis_and_cig(metar_string):
    vis_val, cig_val = 10.0, 10000 
    if "Error" in metar_string or "No recent" in metar_string or not metar_string: return vis_val, cig_val
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
        except: pass 
    cig_match = re.search(r'(BKN|OVC|VV)(\d{3})', metar_string)
    if cig_match: cig_val = int(cig_match.group(2)) * 100
    return vis_val, cig_val

def check_speci(old_val, new_val, thresholds):
    for t in thresholds:
        if (old_val >= t and new_val < t) or (old_val < t and new_val >= t): return True, t
    return False, None

vis_thresholds = [3.0, 2.0, 1.0, 0.5, 0.25]
cig_thresholds = [3000, 1500, 1000, 500, 200]

# --- COMM CHECK UI ---
st.markdown("### 📡 System Comm Status (5-Min Early Warning)")
latest_raw, latest_ts, live_temp_c, live_dew_c, diag_err = get_5min_asos()

if latest_raw and latest_ts:
    try:
        ob_time = datetime.fromisoformat(latest_ts.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        age_minutes = (now - ob_time).total_seconds() / 60

        col_a, col_b = st.columns([2, 1])
        with col_a: st.code(f"{latest_raw}", language="bash")
        with col_b:
            if age_minutes > 20: st.error(f"🚨 **COMM WARNING:** Ping is **{int(age_minutes)} mins old!** Check long-line.")
            else: st.success(f"✅ **Comms Good:** Latency is **{int(age_minutes)}** mins.")
    except Exception as e: st.warning("Could not calculate age.")
else: st.warning(f"⚠️ 5-minute network ping unavailable. Diagnostic code: {diag_err}")

st.divider()

# --- TOP UI: OBSERVATIONS & RADAR ---
top_col1, top_col2 = st.columns([1, 1])

with top_col1:
    tab_local, tab_regional = st.tabs(["📍 KBHM Transmitted", "🌍 Regional 5-Min (50-mi)"])
    
    with tab_local:
        awc_data = get_awc_data()
        recent_metars = [obs.get('rawOb', 'No raw string') for obs in awc_data[:6]] if awc_data else ["No recent METARs found."]
        latest_metar = recent_metars[0] if len(recent_metars) > 0 else ""
        live_vis, live_cig = extract_vis_and_cig(latest_metar)
        
        if "No recent" not in latest_metar:
            for i, metar in enumerate(recent_metars):
                if i == 0: st.error(f"**LATEST:** `{metar}`")
                elif i == 1: st.warning(f"`{metar}`")
                else: st.info(f"`{metar}`")
        else: st.warning("Could not load AWC METARs.")

    with tab_regional:
        st.markdown("**Last Hour of 5-Minute ASOS Data**")
        if st.button("Fetch Fresh Regional Data"):
            with st.spinner("Pulling regional observations..."):
                reg_data = get_regional_5min()
                for stn, reg_obs_list in reg_data.items():
                    st.markdown(f"**{stn}**")
                    for ob in reg_obs_list:
                        st.caption(f"`{ob}`")

with top_col2:
    st.markdown("#### 📡 Live Radar (KBMX)")
    st.image("https://radar.weather.gov/ridge/standard/KBMX_loop.gif", caption="Live NWS Birmingham (BMX) Radar Loop", use_container_width=True)

st.divider()

# --- MIDDLE UI: SPECI & CLOUD CALCULATORS ---
st.subheader("🧮 JO 7900.5E Calculators")

calc_col1, calc_col2, calc_col3 = st.columns(3)

with calc_col1:
    st.markdown("**🌫️ Visibility SPECI**")
    old_vis = st.number_input("Prev Vis (SM)", min_value=0.0, value=10.0, step=0.25)
    new_vis = st.number_input("Cur Vis (SM)", min_value=0.0, value=float(live_vis), step=0.25)
    vis_speci, vis_trigger = check_speci(old_vis, new_vis, vis_thresholds)
    if old_vis != new_vis:
        if vis_speci: st.error(f"🚨 **SPECI REQUIRED:** Crossed {vis_trigger} SM.")
        else: st.success("✅ No SPECI required.")

with calc_col2:
    st.markdown("**☁️ Ceiling SPECI**")
    old_cig = st.number_input("Prev Ceiling (Ft)", min_value=0, value=5000, step=100)
    new_cig = st.number_input("Cur Ceiling (Ft)", min_value=0, value=int(live_cig), step=100)
    cig_speci, cig_trigger = check_speci(old_cig, new_cig, cig_thresholds)
    if old_cig != new_cig:
        if cig_speci: st.error(f"🚨 **SPECI REQUIRED:** Crossed {cig_trigger} FT.")
        else: st.success("✅ No SPECI required.")

with calc_col3:
    st.markdown("**☁️ Convective Cloud Base**")
    if live_temp_c is not None and live_dew_c is not None:
        t_f = (live_temp_c * 9/5) + 32
        d_f = (live_dew_c * 9/5) + 32
        spread_f = t_f - d_f
        ccl_agl = int(spread_f * 230)
        st.info(f"**Live Spread:** {int(spread_f)}°F")
        st.success(f"**Suggested Base:** {ccl_agl} ft AGL")
    else: st.warning("Awaiting live Temp/Dew data...")

st.divider()

# --- BOTTOM UI: REMARKS (RMK) BUILDER ---
st.subheader("📝 Remarks (RMK) Builder (A-Z Strict Order)")
st.caption("Select weather phenomena. The system will automatically sort them into the exact order required by the BHM Cheat Sheet.")

tab_svr, tab_wind, tab_ts, tab_precip = st.tabs(["🌪️ Severe Wx", "💨 Wind/Pressure", "🌩️ TS & Lightning", "🌧️ Precip/Hail/Virga"])

rmks = {letter: "" for letter in "ABCDEFGHIJKLMNOPQRSTUVW"}

with tab_svr:
    col_a, col_b = st.columns(2)
    with col_a:
        has_torn = st.checkbox("Tornadic Activity")
        if has_torn:
            st.error("🚨 MAIN OBS REMINDER: Add `+FC` (Tornado/Waterspout) or `FC` (Funnel Cloud) to Present WX.")
            torn_type = st.selectbox("Type:", ["TORNADO", "FUNNEL CLOUD", "WATERSPOUT"])
            torn_b = st.text_input("Begin Time (Min past HR):", "")
            torn_e = st.text_input("End Time (Min past HR):", "")
            torn_loc = st.selectbox("Location:", ["", "ALQDS", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])
            torn_mov = st.selectbox("Moving:", ["", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])
            
            t_str = f"{torn_type}"
            if torn_b: t_str += f" B{torn_b}"
            if torn_e: t_str += f" E{torn_e}"
            if torn_loc: t_str += f" {torn_loc}"
            if torn_mov: t_str += f" MOV {torn_mov}"
            rmks['B'] = t_str

    with col_b:
        has_volc = st.checkbox("Volcanic Eruption")
        if has_volc:
            st.error("🚨 MAIN OBS REMINDER: Add `VA` to Present WX.")
            volc_name = st.text_input("Volcano Name:")
            if volc_name: rmks['A'] = f"MT {volc_name.upper()} ERUPTION"

with tab_wind:
    col_w1, col_w2, col_w3 = st.columns(3)
    with col_w1:
        has_pk_wnd = st.checkbox("Peak Wind (>25kt)")
        if has_pk_wnd:
            pk_dir = st.number_input("Direction", min_value=0, max_value=360, step=10, value=270)
            pk_spd = st.number_input("Speed (Kts)", min_value=26, max_value=200, step=1, value=35)
            pk_time = st.number_input("Time (Min)", min_value=0, max_value=59, step=1, value=15)
            rmks['C'] = f"PK WND {pk_dir:03d}{pk_spd}/{pk_time:02d}"
    with col_w2:
        has_wshft = st.checkbox("Wind Shift")
        if has_wshft:
            wshft_time = st.number_input("Shift Time (Min)", min_value=0, max_value=59, step=1, value=15)
            fropa = st.checkbox("FROPA (Frontal Passage)")
            w_str = f"WSHFT {wshft_time:02d}"
            if fropa: w_str += " FROPA"
            rmks['D'] = w_str
    with col_w3:
        pressure_rmk = st.radio("Pressure Trend:", ["None", "Rising Rapidly", "Falling Rapidly"])
        if pressure_rmk == "Rising Rapidly": rmks['R'] = "PRESRR"
        elif pressure_rmk == "Falling Rapidly": rmks['R'] = "PRESFR"

with tab_ts:
    col_ts1, col_ts2 = st.columns(2)
    with col_ts1:
        has_ltg = st.checkbox("Lightning Observed")
        if has_ltg:
            ltg_freq = st.selectbox("Frequency:", ["OCNL", "FRQ", "CONS"])
            ltg_types = st.multiselect("Type:", ["IC", "CG", "CC", "CA"], default=["CG"])
            ltg_loc = st.selectbox("LTG Location:", ["ALQDS", "OHD", "VC", "DSNT", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])
            type_str = "".join(ltg_types)
            rmks['H'] = f"{ltg_freq} LTG{type_str} {ltg_loc}"
            
    with col_ts2:
        has_ts = st.checkbox("Thunderstorm Active")
        if has_ts:
            st.warning("🚨 **TS REMINDER:** Put `TS` in Pres WX | Add `CB` to Sky | Turn ALDARS to `MAN`")
            ts_loc = st.selectbox("TS Location:", ["OHD", "VC", "DSNT", "ALQDS", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])
            ts_mov = st.selectbox("TS Moving:", ["Unknown", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])
            ts_str = f"TS {ts_loc}"
            if ts_mov != "Unknown": ts_str += f" MOV {ts_mov}"
            rmks['K'] = ts_str

with tab_precip:
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        has_precip = st.checkbox("Precipitation Begin/End")
        if has_precip:
            p_type = st.selectbox("Precip Type:", ["RA", "SN", "DZ", "UP"])
            p_b = st.text_input("B (Min past HR):", "")
            p_e = st.text_input("E (Min past HR):", "")
            p_str = f"{p_type}"
            if p_b: p_str += f"B{p_b}"
            if p_e: p_str += f"E{p_e}"
            rmks['I'] = p_str
    with col_p2:
        has_hail = st.checkbox("Hail")
        if has_hail:
            st.error("🚨 MAIN OBS REMINDER: `GR` (>=1/4 in) or `GS` (<1/4 in).")
            hail_size = st.text_input("Hail Size (Inches, e.g., 1/2, 1 1/4):", "1/4")
            rmks['L'] = f"GR {hail_size}"
    with col_p3:
        has_virga = st.checkbox("VIRGA")
        if has_virga:
            virga_loc = st.selectbox("Virga Loc:", ["ALQDS", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])
            if virga_loc == "ALQDS": rmks['M'] = "VIRGA ALQDS"
            else: rmks['M'] = f"VIRGA {virga_loc}"

st.markdown("---")

final_remarks = []
for key in sorted(rmks.keys()):
    if rmks[key] != "":
        final_remarks.append(rmks[key])

if final_remarks:
    st.success("**Final JO 7900.5E Remark String (Correct Order):**")
    st.code("RMK " + " ".join(final_remarks), language="markdown")
else:
    st.info("Select weather events in the tabs above to build your remarks string.")

st.divider()

# --- PDF SEARCH ENGINE WITH VIEWER ---
st.subheader("📚 JO 7900.5E Reference Manual")
st.markdown("Search the official FAA Surface Weather Observing manual instantly, or view it directly.")

# Bypass base64 limits completely by telling the browser to fetch the PDF directly from GitHub
pdf_url = "https://cdn.jsdelivr.net/gh/erichattendorf/CWO_Dashboard@main/Order_JO_7900.5E.pdf"

with st.expander("📖 Click Here to Browse the Full JO 7900.5E Manual"):
    # This embeds the raw PDF URL directly so the browser native viewer kicks in
    st.markdown(f'<iframe src="{pdf_url}" width="100%" height="800" type="application/pdf"></iframe>', unsafe_allow_html=True)

st.markdown("---")
search_query = st.text_input("🔍 Search keyword (e.g., 'Freezing Drizzle', 'Tornado', 'SPECI'):")

if search_query:
    if os.path.exists("Order_JO_7900.5E.pdf"):
        with st.spinner(f"Scanning JO 7900.5E for '{search_query}'..."):
            try:
                # We still use PyPDF2 just to find WHICH page the keyword is on
                reader = PyPDF2.PdfReader("Order_JO_7900.5E.pdf")
                results = []
                for i, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if text and search_query.lower() in text.lower():
                        idx = text.lower().find(search_query.lower())
                        start = max(0, idx - 40)
                        end = min(len(text), idx + 40)
                        snippet = text[start:end].replace('\n', ' ')
                        results.append((i+1, snippet))
                
                if results:
                    st.success(f"✅ Found {len(results)} matching pages!")
                    
                    # Create a dropdown to select which page to view
                    match_dict = {f"Page {p} ( ...{snip}... )": p for p, snip in results}
                    selected_match = st.selectbox("Select a match to view the document:", list(match_dict.keys()))
                    
                    if selected_match:
                        target_page = match_dict[selected_match]
                        # Use the CDN link but append #page=X to jump straight to the exact page inside the viewer
                        pdf_display = f'<iframe src="{pdf_url}#page={target_page}" width="100%" height="800" type="application/pdf"></iframe>'
                        st.markdown(pdf_display, unsafe_allow_html=True)
                else:
                    st.warning("No results found in the manual.")
            except Exception as e:
                st.error(f"Error reading PDF. ({e})")
    else:
        st.error("⚠️ `Order_JO_7900.5E.pdf` not found in folder!")