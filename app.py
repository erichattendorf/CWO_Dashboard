import streamlit as st
import streamlit.components.v1 as components
import requests
import re
from datetime import datetime, timezone
import os
import fitz  # PyMuPDF for high-res PDF rendering

# --- PAGE SETUP ---
st.set_page_config(page_title="BHM CWO Dashboard", layout="wide", initial_sidebar_state="expanded")

# --- INITIALIZE SESSION STATE FOR PDF VIEWER ---
if "pdf_page" not in st.session_state:
    st.session_state.pdf_page = 0

# --- SIDEBAR: METAR ALARM ---
with st.sidebar:
    st.title("⏰ METAR Alarm")
    st.markdown("Alerts before the XX:53 observation.")
    
    alarm_enabled = st.toggle("Enable Alarm", value=True)
    
    if alarm_enabled:
        alarm_minute = st.number_input("Trigger at XX past hour:", min_value=0, max_value=59, value=48, step=1)
        
        sound_choices = [
            "1. SOS Morse Code", "2. Classic Triple Beep", "3. Two-Tone Warning", 
            "4. Gentle Chimes", "5. Submarine Ping", "6. Harsh Buzzer", 
            "7. Digital Watch", "8. Air Raid Siren", "9. Radar Sweep", "10. Urgent Trill",
            "11. Telephone Ring", "12. Sci-Fi Alarm", "13. EKG Heart Monitor", 
            "14. Fast Geiger", "15. Deep Foghorn"
        ]
        alarm_sound = st.selectbox("Sound Profile:", sound_choices)
        sound_id = int(alarm_sound.split(".")[0])
        
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            alarm_vol = st.slider("Vol %", min_value=1, max_value=100, value=50, step=1)
        with col_v2:
            alarm_pitch = st.slider("Pitch %", min_value=50, max_value=200, value=100, step=10)

        # JavaScript to Auto-Expand the Sidebar and Sound the Alarm
        alarm_html = f"""
        <div id="idle-box" style="text-align:center; font-family:sans-serif; border-radius: 10px; padding: 15px; margin-top: 10px; background: #f0f2f6; border: 1px solid #ddd;">
            <h3 style="color: #333; margin: 0 0 10px 0; font-size: 16px;">Monitoring for XX:{alarm_minute:02d}</h3>
            <button onclick="triggerAlarmUI(true)" style="padding: 8px 15px; border-radius: 5px; border: 1px solid #aaa; cursor: pointer; background: white; font-weight: bold; color: #333;">🔊 Test Sound</button>
            <p style="font-size: 10px; color: gray; margin-top: 8px;">(Click 'Test' once to authorize audio)</p>
        </div>

        <div id="alert-box" style="display:none; background-color: #ff4b4b; color: white; padding: 20px; border-radius: 10px; text-align: center; margin-top: 10px; box-shadow: 0px 4px 10px rgba(0,0,0,0.3);">
            <h2 style="margin: 0; font-size: 24px; font-family: sans-serif;">🚨 ALARM 🚨</h2>
            <h3 style="margin: 5px 0 15px 0; font-size: 16px; font-weight: normal;">Observation Due!</h3>
            <button onclick="silenceAlarm()" style="padding: 15px; font-size: 16px; font-weight: bold; color: #ff4b4b; background: white; border: none; border-radius: 5px; cursor: pointer; width: 100%; box-shadow: 0px 2px 5px rgba(0,0,0,0.2);">
                🔕 Silence Current Alarm
            </button>
        </div>

        <script>
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        let audioCtx;
        let activeOscillators = [];
        let alarmInterval;
        let isSilencedForThisMinute = false;
        const originalTitle = "BHM CWO Dashboard";
        let titleFlashInterval;

        function playTone(freq, type, startDelay, duration, vol) {{
            const pitchMult = {alarm_pitch} / 100.0;
            const finalFreq = freq * pitchMult;
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.type = type;
            osc.frequency.value = finalFreq;
            osc.connect(gain);
            gain.connect(audioCtx.destination);
            
            const t = audioCtx.currentTime + startDelay;
            gain.gain.setValueAtTime(0, t);
            gain.gain.linearRampToValueAtTime(vol, t + 0.02);
            gain.gain.setValueAtTime(vol, t + duration - 0.02);
            gain.gain.linearRampToValueAtTime(0, t + duration);
            
            osc.start(t);
            osc.stop(t + duration);
            activeOscillators.push(osc);
        }}

        function playAlarmAudio() {{
            if (!audioCtx) audioCtx = new AudioContext();
            if (audioCtx.state === 'suspended') audioCtx.resume();
            
            activeOscillators.forEach(osc => {{ try {{ osc.stop(); }} catch(e){{}} }});
            activeOscillators = [];

            const rawVol = {alarm_vol} / 100.0;
            const v = Math.pow(rawVol, 2);
            const s = {sound_id};

            if (s === 1) {{ 
                let t = 0;
                for(let i=0; i<3; i++) {{
                    playTone(700, 'sine', t, 0.1, v); playTone(700, 'sine', t+0.2, 0.1, v); playTone(700, 'sine', t+0.4, 0.1, v); t += 0.8;
                    playTone(700, 'sine', t, 0.3, v); playTone(700, 'sine', t+0.4, 0.3, v); playTone(700, 'sine', t+0.8, 0.3, v); t += 1.3;
                    playTone(700, 'sine', t, 0.1, v); playTone(700, 'sine', t+0.2, 0.1, v); playTone(700, 'sine', t+0.4, 0.1, v); t += 1.5;
                }}
            }} 
            else if (s === 2) {{ playTone(800, 'sine', 0, 0.15, v); playTone(800, 'sine', 0.3, 0.15, v); playTone(800, 'sine', 0.6, 0.15, v); }}
            else if (s === 3) {{ for(let i=0; i<4; i++) {{ playTone(600, 'square', i*1.0, 0.5, v*0.5); playTone(800, 'square', (i*1.0)+0.5, 0.5, v*0.5); }} }}
            else if (s === 4) {{ playTone(523.25, 'sine', 0, 0.4, v); playTone(659.25, 'sine', 0.3, 0.4, v); playTone(783.99, 'sine', 0.6, 0.8, v); }}
            else if (s === 5) {{ playTone(1000, 'sine', 0, 0.1, v); playTone(1000, 'sine', 0.1, 1.5, v*0.1); }}
            else if (s === 6) {{ playTone(150, 'sawtooth', 0, 0.5, v); playTone(150, 'sawtooth', 0.8, 0.5, v); playTone(150, 'sawtooth', 1.6, 0.5, v); }}
            else if (s === 7) {{ playTone(2000, 'square', 0, 0.08, v*0.2); playTone(2000, 'square', 0.15, 0.08, v*0.2); playTone(2000, 'square', 1.0, 0.08, v*0.2); playTone(2000, 'square', 1.15, 0.08, v*0.2); }}
            else if (s === 8) {{
                const osc = audioCtx.createOscillator(); const gain = audioCtx.createGain();
                osc.type = 'sine'; osc.connect(gain); gain.connect(audioCtx.destination);
                const pitchMult = {alarm_pitch} / 100.0;
                gain.gain.setValueAtTime(0, audioCtx.currentTime); gain.gain.linearRampToValueAtTime(v, audioCtx.currentTime + 0.5);
                gain.gain.setValueAtTime(v, audioCtx.currentTime + 3.5); gain.gain.linearRampToValueAtTime(0, audioCtx.currentTime + 4.0);
                osc.frequency.setValueAtTime(400 * pitchMult, audioCtx.currentTime); osc.frequency.linearRampToValueAtTime(1200 * pitchMult, audioCtx.currentTime + 2);
                osc.frequency.linearRampToValueAtTime(400 * pitchMult, audioCtx.currentTime + 4);
                osc.start(audioCtx.currentTime); osc.stop(audioCtx.currentTime + 4.0); activeOscillators.push(osc);
            }}
            else if (s === 9) {{ for(let i=0; i<3; i++) {{ playTone(900, 'triangle', i*1.5, 0.1, v); }} }}
            else if (s === 10) {{ for(let i=0; i<15; i++) {{ playTone(i%2==0 ? 700 : 750, 'square', i*0.1, 0.08, v*0.5); }} }}
            else if (s === 11) {{ for(let i=0; i<6; i++) {{ playTone(1200, 'sine', i*0.15, 0.05, v); playTone(1500, 'sine', i*0.15+0.05, 0.05, v); }} }}
            else if (s === 12) {{
                for(let i=0; i<5; i++) {{
                    const osc = audioCtx.createOscillator(); const gain = audioCtx.createGain();
                    osc.type = 'sawtooth'; osc.connect(gain); gain.connect(audioCtx.destination);
                    const pitchMult = {alarm_pitch} / 100.0;
                    gain.gain.setValueAtTime(v, audioCtx.currentTime + (i*0.5)); gain.gain.linearRampToValueAtTime(0, audioCtx.currentTime + (i*0.5) + 0.4);
                    osc.frequency.setValueAtTime(1500 * pitchMult, audioCtx.currentTime + (i*0.5)); osc.frequency.linearRampToValueAtTime(300 * pitchMult, audioCtx.currentTime + (i*0.5) + 0.4);
                    osc.start(audioCtx.currentTime + (i*0.5)); osc.stop(audioCtx.currentTime + (i*0.5) + 0.4); activeOscillators.push(osc);
                }}
            }}
            else if (s === 13) {{ playTone(900, 'sine', 0, 0.1, v); playTone(900, 'sine', 1.0, 0.1, v); playTone(900, 'sine', 2.0, 0.1, v); }}
            else if (s === 14) {{ for(let i=0; i<20; i++) {{ playTone(2000, 'square', i*0.1 + (Math.random()*0.05), 0.02, v*0.2); }} }}
            else if (s === 15) {{ playTone(100, 'sawtooth', 0, 2.0, v); playTone(102, 'square', 0, 2.0, v*0.5); }}
        }}

        function triggerAlarmUI(isTest = false) {{
            // Automatically open the sidebar if it is closed!
            try {{
                const expandBtn = window.parent.document.querySelector('[data-testid="collapsedControl"]');
                if (expandBtn) {{ expandBtn.click(); }}
            }} catch(e) {{}}

            document.getElementById('idle-box').style.display = 'none';
            document.getElementById('alert-box').style.display = 'block';
            playAlarmAudio();
            
            if (!isTest) {{ 
                alarmInterval = setInterval(playAlarmAudio, 5000); 
                try {{
                    let flashState = false;
                    titleFlashInterval = setInterval(() => {{
                        window.parent.document.title = flashState ? "🚨 ALARM 🚨" : "OBSERVATION DUE!";
                        flashState = !flashState;
                    }}, 1000);
                }} catch(e) {{}}
            }}
        }}

        function silenceAlarm() {{
            clearInterval(alarmInterval);
            clearInterval(titleFlashInterval);
            try {{ window.parent.document.title = originalTitle; }} catch(e) {{}}
            
            activeOscillators.forEach(osc => {{ try {{ osc.stop(); }} catch(e){{}} }});
            activeOscillators = [];
            document.getElementById('alert-box').style.display = 'none';
            document.getElementById('idle-box').style.display = 'block';
            isSilencedForThisMinute = true;
        }}

        let hasTriggeredThisHour = false;
        setInterval(function() {{
            var d = new Date();
            if (d.getMinutes() === {alarm_minute}) {{
                if (!hasTriggeredThisHour && !isSilencedForThisMinute) {{
                    triggerAlarmUI(false);
                    hasTriggeredThisHour = true;
                }}
            }} else {{
                hasTriggeredThisHour = false; 
                isSilencedForThisMinute = false;
                document.getElementById('alert-box').style.display = 'none';
                document.getElementById('idle-box').style.display = 'block';
            }}
        }}, 1000);
        </script>
        """
        components.html(alarm_html, height=220)
    else:
        st.info("🔕 Alarm is currently disabled.")

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
    timestamp = props.get('timestamp')
    if not timestamp: return None, None, None, None
    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    time_str = dt.strftime("%H:%MZ")
    
    try:
        temp_c = float(props.get('temperature', {}).get('value'))
        dew_c = float(props.get('dewpoint', {}).get('value'))
    except (TypeError, ValueError): temp_c, dew_c = None, None

    wdir = props.get('windDirection', {}).get('value')
    wspd_kmh = props.get('windSpeed', {}).get('value')
    wdir_str = f"{int(wdir):03d}" if wdir is not None else "VRB"
    wspd_kts = int(round(wspd_kmh / 1.852)) if wspd_kmh is not None else 0
    wind_str = f"{wdir_str}@{wspd_kts}kt"
    
    vis_m = props.get('visibility', {}).get('value')
    vis_sm = round(vis_m / 1609.34, 1) if vis_m is not None else "M"
    
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
        if desc and "Clear" in desc: clouds_str = "CLR"
        else: clouds_str = "M"
            
    temp_str = f"{int(temp_c)}" if temp_c is not None else "M"
    dew_str = f"{int(dew_c)}" if dew_c is not None else "M"
    pres_pa = props.get('barometricPressure', {}).get('value')
    pres_inhg = round(pres_pa / 3386.389, 2) if pres_pa is not None else "M"
    
    formatted_str = f"({time_str}) | Wind: {wind_str} | Vis: {vis_sm}SM | Sky: {clouds_str} | Temp/Dew: {temp_str}/{dew_str}°C | Alt: {pres_inhg} inHg"
    return formatted_str, timestamp, temp_c, dew_c

def get_5min_asos():
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
                    final_raw = f"BHM 5-MIN ({timestamp[11:16]}Z) | {raw}" if raw else f"BHM 5-MIN {formatted_str}"
                    return final_raw, timestamp, temp_c, dew_c, None
            return None, None, None, None, "No data features found in NWS ping."
        else: return None, None, None, None, f"HTTP {response.status_code}"
    except Exception as e: return None, None, None, None, f"Error: {str(e)}"

def get_regional_5min():
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
                        parsed.append(f"({ts[11:16]}Z) | {raw}" if raw else formatted_str)
                data[stn] = parsed
            else: data[stn] = [f"API Error: HTTP {res.status_code}"]
        except: data[stn] = ["Connection Error"]
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
            else: vis_val = float(vis_str)
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
    except: st.warning("Could not calculate age.")
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
                for stn, obs_list in reg_data.items():
                    st.markdown(f"**{stn}**")
                    for ob in obs_list: st.caption(f"`{ob}`")

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
        temp_c_int = round(live_temp_c)
        dew_c_int = round(live_dew_c)
        t_f, d_f = (temp_c_int * 9/5) + 32, (dew_c_int * 9/5) + 32
        spread_f = t_f - d_f
        ccl_agl = int(round((spread_f * 230) / 100.0)) * 100
        st.info(f"**Live Spread:** {int(spread_f)}°F (using {temp_c_int}C/{dew_c_int}C)")
        st.success(f"**Suggested Base:** {ccl_agl} ft AGL")
    else: st.warning("Awaiting live Temp/Dew data...")

st.divider()

# --- BOTTOM UI: REMARKS (RMK) BUILDER ---
st.subheader("📝 Remarks (RMK) Builder (A-Z Strict Order)")
tab_svr, tab_wind, tab_ts, tab_precip = st.tabs(["🌪️ Severe Wx", "💨 Wind/Pressure", "🌩️ TS & Lightning", "🌧️ Precip/Hail/Virga"])
rmks = {letter: "" for letter in "ABCDEFGHIJKLMNOPQRSTUVW"}

with tab_svr:
    col_a, col_b = st.columns(2)
    with col_a:
        has_torn = st.checkbox("Tornadic Activity")
        if has_torn:
            st.error("🚨 MAIN OBS REMINDER: Add `+FC` or `FC` to Present WX.")
            torn_type = st.selectbox("Type:", ["TORNADO", "FUNNEL CLOUD", "WATERSPOUT"])
            torn_b, torn_e = st.text_input("Begin Time (Min):", ""), st.text_input("End Time (Min):", "")
            torn_loc, torn_mov = st.selectbox("Location:", ["", "ALQDS", "N", "NE", "E", "SE", "S", "SW", "W", "NW"]), st.selectbox("Moving:", ["", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])
            t_str = f"{torn_type}" + (f" B{torn_b}" if torn_b else "") + (f" E{torn_e}" if torn_e else "") + (f" {torn_loc}" if torn_loc else "") + (f" MOV {torn_mov}" if torn_mov else "")
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
            pk_dir, pk_spd, pk_time = st.number_input("Direction", min_value=0, max_value=360, step=10, value=270), st.number_input("Speed (Kts)", min_value=26, max_value=200, step=1, value=35), st.number_input("Time (Min)", min_value=0, max_value=59, step=1, value=15)
            rmks['C'] = f"PK WND {pk_dir:03d}{pk_spd}/{pk_time:02d}"
    with col_w2:
        has_wshft = st.checkbox("Wind Shift")
        if has_wshft:
            wshft_time = st.number_input("Shift Time (Min)", min_value=0, max_value=59, step=1, value=15)
            rmks['D'] = f"WSHFT {wshft_time:02d}" + (" FROPA" if st.checkbox("FROPA") else "")
    with col_w3:
        pressure_rmk = st.radio("Pressure Trend:", ["None", "Rising Rapidly", "Falling Rapidly"])
        if pressure_rmk == "Rising Rapidly": rmks['R'] = "PRESRR"
        elif pressure_rmk == "Falling Rapidly": rmks['R'] = "PRESFR"

with tab_ts:
    col_ts1, col_ts2 = st.columns(2)
    with col_ts1:
        has_ltg = st.checkbox("Lightning Observed")
        if has_ltg:
            ltg_freq, ltg_types, ltg_loc = st.selectbox("Frequency:", ["OCNL", "FRQ", "CONS"]), st.multiselect("Type:", ["IC", "CG", "CC", "CA"], default=["CG"]), st.selectbox("LTG Location:", ["ALQDS", "OHD", "VC", "DSNT", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])
            rmks['H'] = f"{ltg_freq} LTG{''.join(ltg_types)} {ltg_loc}"
    with col_ts2:
        has_ts = st.checkbox("Thunderstorm Active")
        if has_ts:
            st.warning("🚨 **TS REMINDER:** Put `TS` in Pres WX | Add `CB` to Sky | Turn ALDARS to `MAN`")
            ts_loc, ts_mov = st.selectbox("TS Location:", ["OHD", "VC", "DSNT", "ALQDS", "N", "NE", "E", "SE", "S", "SW", "W", "NW"]), st.selectbox("TS Moving:", ["Unknown", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])
            rmks['K'] = f"TS {ts_loc}" + (f" MOV {ts_mov}" if ts_mov != "Unknown" else "")

with tab_precip:
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        has_precip = st.checkbox("Precipitation Begin/End")
        if has_precip:
            p_type, p_b, p_e = st.selectbox("Precip Type:", ["RA", "SN", "DZ", "UP"]), st.text_input("B (Min past HR):", ""), st.text_input("E (Min past HR):", "")
            rmks['I'] = f"{p_type}" + (f"B{p_b}" if p_b else "") + (f"E{p_e}" if p_e else "")
    with col_p2:
        has_hail = st.checkbox("Hail")
        if has_hail:
            st.error("🚨 MAIN OBS REMINDER: `GR` (>=1/4 in) or `GS` (<1/4 in).")
            rmks['L'] = f"GR {st.text_input('Hail Size:', '1/4')}"
    with col_p3:
        has_virga = st.checkbox("VIRGA")
        if has_virga:
            virga_loc = st.selectbox("Virga Loc:", ["ALQDS", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])
            rmks['M'] = "VIRGA ALQDS" if virga_loc == "ALQDS" else f"VIRGA {virga_loc}"

st.markdown("---")
final_remarks = [rmks[key] for key in sorted(rmks.keys()) if rmks[key] != ""]
if final_remarks:
    st.success("**Final JO 7900.5E Remark String (Correct Order):**")
    st.code("RMK " + " ".join(final_remarks), language="markdown")

st.divider()

# --- PDF SEARCH ENGINE WITH CUSTOM IMAGE PAGINATOR ---
st.subheader("📚 JO 7900.5E Reference Manual")
st.markdown("Search the official FAA Surface Weather Observing manual instantly. Pages are rendered securely as images.")

if os.path.exists("Order_JO_7900.5E.pdf"):
    search_query = st.text_input("🔍 Search keyword (e.g., 'Freezing Drizzle', 'Tornado', 'SPECI'):")
    
    if search_query:
        with st.spinner(f"Scanning JO 7900.5E for '{search_query}'..."):
            try:
                doc = fitz.open("Order_JO_7900.5E.pdf")
                results = []
                for i in range(len(doc)):
                    text = doc[i].get_text()
                    if search_query.lower() in text.lower():
                        idx = text.lower().find(search_query.lower())
                        start = max(0, idx - 40)
                        snippet = text[start:min(len(text), idx + 40)].replace('\n', ' ')
                        results.append((i, snippet))
                
                if results:
                    st.success(f"✅ Found {len(results)} matching pages!")
                    match_dict = {f"Page {p+1} ( ...{snip}... )": p for p, snip in results}
                    
                    # Layout for selecting a match
                    selected_match = st.selectbox("Select a match to start reading from:", list(match_dict.keys()))
                    
                    if st.button("Load This Page"):
                        # Save the target page to session state so we can scroll from there!
                        st.session_state.pdf_page = match_dict[selected_match]
                        
                else: 
                    st.warning("No results found.")
            except Exception as e: 
                st.error(f"Error reading PDF. Are you sure you updated requirements.txt? ({e})")

    # Render the Interactive Image Viewer
    if "pdf_page" in st.session_state and st.session_state.pdf_page >= 0:
        try:
            doc = fitz.open("Order_JO_7900.5E.pdf")
            total_pages = len(doc)
            
            # Boundary protections
            if st.session_state.pdf_page < 0:
                st.session_state.pdf_page = 0
            elif st.session_state.pdf_page >= total_pages:
                st.session_state.pdf_page = total_pages - 1
            
            st.markdown("---")
            
            # The Paginator Controls
            col_p1, col_p2, col_p3 = st.columns([1, 2, 1])
            with col_p1:
                if st.button("⬅️ Previous Page") and st.session_state.pdf_page > 0:
                    st.session_state.pdf_page -= 1
                    st.rerun()
            with col_p2:
                st.markdown(f"<div style='text-align: center; font-weight: bold;'>Currently Viewing Page {st.session_state.pdf_page + 1} of {total_pages}</div>", unsafe_allow_html=True)
            with col_p3:
                if st.button("Next Page ➡️") and st.session_state.pdf_page < total_pages - 1:
                    st.session_state.pdf_page += 1
                    st.rerun()

            # Render the specific page as a crisp image
            page = doc.load_page(st.session_state.pdf_page)
            pix = page.get_pixmap(dpi=150)
            st.image(pix.tobytes("png"), use_container_width=True)
            
        except Exception as e:
            st.error("Error loading document view.")
            
else: 
    st.error("⚠️ `Order_JO_7900.5E.pdf` not found in folder!")