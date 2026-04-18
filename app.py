import streamlit as st
import streamlit.components.v1 as components
import requests
import re
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import os
import fitz  

# --- PAGE SETUP ---
st.set_page_config(page_title="BHM CWO Dashboard", layout="wide", initial_sidebar_state="expanded")

# --- CSS ---
st.markdown("""
<style>
    [data-testid="collapsedControl"] {
        background-color: #ff4b4b !important;
        color: white !important;
        border-radius: 0 8px 8px 0 !important;
        padding: 5px 15px 5px 10px !important;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.3) !important;
        width: auto !important;
        transition: 0.2s !important;
    }
    [data-testid="collapsedControl"]::after {
        content: " 🚨 ALERTS";
        font-family: sans-serif;
        font-weight: bold;
        font-size: 16px;
        margin-left: 5px;
    }
    [data-testid="collapsedControl"]:hover { background-color: #cc0000 !important; }
    [data-testid="collapsedControl"] title { display: none !important; }
    .flight-cat-banner {
        padding: 12px 20px; border-radius: 8px; font-size: 22px;
        font-weight: bold; text-align: center; margin-bottom: 8px;
        letter-spacing: 2px; font-family: monospace;
    }
</style>
""", unsafe_allow_html=True)

# --- INITIALIZE SESSION STATE ---
if "pdf_page" not in st.session_state:
    st.session_state.pdf_page = 0
if "turnover_notes" not in st.session_state:
    st.session_state.turnover_notes = {}

# ── SHIFT DETERMINATION (Central Time) ──────────────────────────────────────
bhm_tz = ZoneInfo("America/Chicago")
now_ct = datetime.now(bhm_tz)
hour = now_ct.hour

if 6 <= hour < 14:
    shift_name = "0600 - 1400 (Morning)"
    shift_date = now_ct.strftime("%Y-%m-%d")
elif 14 <= hour < 22:
    shift_name = "1400 - 2200 (Evening)"
    shift_date = now_ct.strftime("%Y-%m-%d")
else:
    shift_name = "2200 - 0600 (Night)"
    # Shift STARTED at 2200: if before midnight use today, if after midnight use yesterday
    shift_date = (now_ct - timedelta(days=1)).strftime("%Y-%m-%d") if hour < 6 else now_ct.strftime("%Y-%m-%d")

current_shift_id = f"{shift_date}_{shift_name}"

# ── SIDEBAR ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📋 Shift Duties")
    st.caption(f"Current Shift: **{shift_name}**")

    checklist_items = [
        "Sign-on OID",
        "Sign-in Contractor & FAA Logs",
        "Receive Shift Briefing",
        "Check Digital T/Td Unit (Charged)",
        "Accomplish METAR/SPECI",
        "Check Read File",
        "Mid-shift: Time-check (Naval Obs)",
        "Mid-shift: Phone check (ATC/TRACON)",
        "QA TWO previous shifts",
        "Review OBS for electronic PMR"
    ]
    for item in checklist_items:
        st.checkbox(item, key=f"chk_{current_shift_id}_{item}")

    st.divider()

    # ── SHIFT TURNOVER NOTES ──────────────────────────────────────────────
    st.title("📝 Shift Turnover Notes")
    st.caption("Write anything the next shift needs to know.")

    prev_shift_map = {
        "0600 - 1400 (Morning)": "2200 - 0600 (Night)",
        "1400 - 2200 (Evening)": "0600 - 1400 (Morning)",
        "2200 - 0600 (Night)":   "1400 - 2200 (Evening)",
    }
    prev_shift_name = prev_shift_map[shift_name]
    prev_shift_date = shift_date  # evening→morning is same date; for night←evening also same date
    if shift_name == "0600 - 1400 (Morning)":
        prev_shift_date = (now_ct - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_shift_id = f"{prev_shift_date}_{prev_shift_name}"

    if prev_shift_id in st.session_state.turnover_notes and st.session_state.turnover_notes[prev_shift_id]:
        st.info(f"**📨 From {prev_shift_name}:**\n\n{st.session_state.turnover_notes[prev_shift_id]}")
    else:
        st.caption("*(No notes from previous shift)*")

    note_key = f"note_input_{current_shift_id}"
    if note_key not in st.session_state:
        st.session_state[note_key] = st.session_state.turnover_notes.get(current_shift_id, "")

    notes_text = st.text_area("Your notes for the next shift:", value=st.session_state[note_key], height=100, key=f"ta_{current_shift_id}")
    if st.button("💾 Save Notes"):
        st.session_state.turnover_notes[current_shift_id] = notes_text
        st.session_state[note_key] = notes_text
        st.success("Notes saved!")

    st.divider()

    # ── METAR ALERTS ─────────────────────────────────────────────────────
    st.title("⏰ METAR Alerts")
    st.markdown("Audio/Visual warnings before the XX:53 observation.")
    alarm_enabled = st.toggle("Enable Alerts", value=False)

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
        with col_v1: alarm_vol   = st.slider("Vol %",   min_value=1,  max_value=100, value=50,  step=1)
        with col_v2: alarm_pitch = st.slider("Pitch %", min_value=50, max_value=200, value=100, step=10)

        alarm_html = f"""
        <div id="idle-box" style="text-align:center; border-radius: 10px; padding: 15px; margin-top: 10px; background: #f0f2f6; border: 1px solid #ddd;">
            <h3 style="color: #333; margin: 0 0 10px 0; font-size: 16px;">Monitoring for XX:{alarm_minute:02d}</h3>
            <button onclick="triggerAlarmUI(true)" style="padding: 8px 15px; border-radius: 5px; border: 1px solid #aaa; cursor: pointer; background: white; font-weight: bold; color: #333;">🔊 Test Alert</button>
            <p style="font-size: 10px; color: gray; margin-top: 8px;">(Click 'Test' once to authorize audio)</p>
        </div>
        <div id="alert-box" style="display:none; background-color: #ff4b4b; color: white; padding: 20px; border-radius: 10px; text-align: center; margin-top: 10px;">
            <h2 style="margin: 0; font-size: 24px; font-family: sans-serif;">🚨 ALARM 🚨</h2>
            <h3 style="margin: 5px 0 15px 0; font-size: 16px; font-weight: normal;">Observation Due!</h3>
            <button onclick="silenceAlarm()" style="padding: 15px; font-size: 16px; font-weight: bold; color: #ff4b4b; background: white; border: none; border-radius: 5px; cursor: pointer; width: 100%;">🔕 Silence Current Alarm</button>
        </div>
        <script>
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        let audioCtx; let activeOscillators = []; let alarmInterval;
        let isSilencedForThisMinute = false;
        const originalTitle = "BHM CWO Dashboard"; let titleFlashInterval;

        function playTone(freq, type, startDelay, duration, vol) {{
            const pitchMult = {alarm_pitch} / 100.0; const finalFreq = freq * pitchMult;
            const osc = audioCtx.createOscillator(); const gain = audioCtx.createGain();
            osc.type = type; osc.frequency.value = finalFreq; osc.connect(gain); gain.connect(audioCtx.destination);
            const t = audioCtx.currentTime + startDelay;
            gain.gain.setValueAtTime(0, t); gain.gain.linearRampToValueAtTime(vol, t + 0.02);
            gain.gain.setValueAtTime(vol, t + duration - 0.02); gain.gain.linearRampToValueAtTime(0, t + duration);
            osc.start(t); osc.stop(t + duration); activeOscillators.push(osc);
        }}
        function playAlarmAudio() {{
            if (!audioCtx) audioCtx = new AudioContext();
            if (audioCtx.state === 'suspended') audioCtx.resume();
            activeOscillators.forEach(osc => {{ try {{ osc.stop(); }} catch(e){{}} }}); activeOscillators = [];
            const rawVol = {alarm_vol} / 100.0; const v = Math.pow(rawVol, 2); const s = {sound_id};
            if (s === 1) {{ let t = 0; for(let i=0; i<3; i++) {{ playTone(700,'sine',t,0.1,v); playTone(700,'sine',t+0.2,0.1,v); playTone(700,'sine',t+0.4,0.1,v); t+=0.8; playTone(700,'sine',t,0.3,v); playTone(700,'sine',t+0.4,0.3,v); playTone(700,'sine',t+0.8,0.3,v); t+=1.3; playTone(700,'sine',t,0.1,v); playTone(700,'sine',t+0.2,0.1,v); playTone(700,'sine',t+0.4,0.1,v); t+=1.5; }} }}
            else if (s===2) {{ playTone(800,'sine',0,0.15,v); playTone(800,'sine',0.3,0.15,v); playTone(800,'sine',0.6,0.15,v); }}
            else if (s===3) {{ for(let i=0;i<4;i++) {{ playTone(600,'square',i*1.0,0.5,v*0.5); playTone(800,'square',(i*1.0)+0.5,0.5,v*0.5); }} }}
            else if (s===4) {{ playTone(523.25,'sine',0,0.4,v); playTone(659.25,'sine',0.3,0.4,v); playTone(783.99,'sine',0.6,0.8,v); }}
            else if (s===5) {{ playTone(1000,'sine',0,0.1,v); playTone(1000,'sine',0.1,1.5,v*0.1); }}
            else if (s===6) {{ playTone(150,'sawtooth',0,0.5,v); playTone(150,'sawtooth',0.8,0.5,v); playTone(150,'sawtooth',1.6,0.5,v); }}
            else if (s===7) {{ playTone(2000,'square',0,0.08,v*0.2); playTone(2000,'square',0.15,0.08,v*0.2); playTone(2000,'square',1.0,0.08,v*0.2); playTone(2000,'square',1.15,0.08,v*0.2); }}
            else if (s===8) {{ const osc=audioCtx.createOscillator(); const gain=audioCtx.createGain(); osc.type='sine'; osc.connect(gain); gain.connect(audioCtx.destination); const pm={alarm_pitch}/100.0; gain.gain.setValueAtTime(0,audioCtx.currentTime); gain.gain.linearRampToValueAtTime(v,audioCtx.currentTime+0.5); gain.gain.setValueAtTime(v,audioCtx.currentTime+3.5); gain.gain.linearRampToValueAtTime(0,audioCtx.currentTime+4.0); osc.frequency.setValueAtTime(400*pm,audioCtx.currentTime); osc.frequency.linearRampToValueAtTime(1200*pm,audioCtx.currentTime+2); osc.frequency.linearRampToValueAtTime(400*pm,audioCtx.currentTime+4); osc.start(audioCtx.currentTime); osc.stop(audioCtx.currentTime+4.0); activeOscillators.push(osc); }}
            else if (s===9) {{ for(let i=0;i<3;i++) {{ playTone(900,'triangle',i*1.5,0.1,v); }} }}
            else if (s===10) {{ for(let i=0;i<15;i++) {{ playTone(i%2==0?700:750,'square',i*0.1,0.08,v*0.5); }} }}
            else if (s===11) {{ for(let i=0;i<6;i++) {{ playTone(1200,'sine',i*0.15,0.05,v); playTone(1500,'sine',i*0.15+0.05,0.05,v); }} }}
            else if (s===12) {{ for(let i=0;i<5;i++) {{ const osc=audioCtx.createOscillator(); const gain=audioCtx.createGain(); osc.type='sawtooth'; osc.connect(gain); gain.connect(audioCtx.destination); const pm={alarm_pitch}/100.0; gain.gain.setValueAtTime(v,audioCtx.currentTime+(i*0.5)); gain.gain.linearRampToValueAtTime(0,audioCtx.currentTime+(i*0.5)+0.4); osc.frequency.setValueAtTime(1500*pm,audioCtx.currentTime+(i*0.5)); osc.frequency.linearRampToValueAtTime(300*pm,audioCtx.currentTime+(i*0.5)+0.4); osc.start(audioCtx.currentTime+(i*0.5)); osc.stop(audioCtx.currentTime+(i*0.5)+0.4); activeOscillators.push(osc); }} }}
            else if (s===13) {{ playTone(900,'sine',0,0.1,v); playTone(900,'sine',1.0,0.1,v); playTone(900,'sine',2.0,0.1,v); }}
            else if (s===14) {{ for(let i=0;i<20;i++) {{ playTone(2000,'square',i*0.1+(Math.random()*0.05),0.02,v*0.2); }} }}
            else if (s===15) {{ playTone(100,'sawtooth',0,2.0,v); playTone(102,'square',0,2.0,v*0.5); }}
        }}
        window.silenceAlarm = function() {{
            clearInterval(alarmInterval); clearInterval(titleFlashInterval);
            try {{ window.parent.document.title = originalTitle; }} catch(e) {{}}
            activeOscillators.forEach(osc => {{ try {{ osc.stop(); }} catch(e){{}} }}); activeOscillators = [];
            document.getElementById('alert-box').style.display = 'none';
            document.getElementById('idle-box').style.display = 'block';
            isSilencedForThisMinute = true;
        }};
        function triggerAlarmUI(isTest = false) {{
            try {{ const parent = window.parent.document; const expandBtn = parent.querySelector('[data-testid="collapsedControl"]'); if (expandBtn && expandBtn.getAttribute('aria-expanded') !== 'true') {{ expandBtn.click(); }} }} catch(e) {{}}
            document.getElementById('idle-box').style.display = 'none';
            document.getElementById('alert-box').style.display = 'block';
            playAlarmAudio();
            if (!isTest) {{ alarmInterval = setInterval(playAlarmAudio, 5000); try {{ let flashState = false; titleFlashInterval = setInterval(() => {{ window.parent.document.title = flashState ? "🚨 ALARM 🚨" : "OBSERVATION DUE!"; flashState = !flashState; }}, 1000); }} catch(e) {{}} }}
        }}
        let hasTriggeredThisHour = false;
        setInterval(function() {{
            var d = new Date();
            if (d.getMinutes() === {alarm_minute}) {{
                if (!hasTriggeredThisHour && !isSilencedForThisMinute) {{ triggerAlarmUI(false); hasTriggeredThisHour = true; }}
            }} else {{ hasTriggeredThisHour = false; isSilencedForThisMinute = false; document.getElementById('alert-box').style.display='none'; document.getElementById('idle-box').style.display='block'; }}
        }}, 1000);
        </script>"""
        components.html(alarm_html, height=180)
    else:
        st.info("🔕 Alerts Disabled.")

# ── HEADER ───────────────────────────────────────────────────────────────────
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

# ── FUNCTIONS ─────────────────────────────────────────────────────────────────
NWS_HEADERS = {"User-Agent": "BHM_CWO_Dashboard/2.0", "Accept": "application/geo+json"}

def get_flight_cat(vis_sm, cig_ft):
    """Returns (category_string, hex_color, bg_hex_color) per FAA flight categories."""
    if vis_sm >= 5 and cig_ft >= 3000:
        return "VFR",  "#ffffff", "#2e7d32"   # green
    elif vis_sm >= 3 and cig_ft >= 1000:
        return "MVFR", "#ffffff", "#1565c0"   # blue
    elif vis_sm >= 1 and cig_ft >= 500:
        return "IFR",  "#ffffff", "#b71c1c"   # red
    else:
        return "LIFR", "#ffffff", "#6a1b9a"   # purple

def calc_density_altitude(temp_c, altimeter_inhg, station_elev_ft):
    """Returns (pressure_alt_ft, density_alt_ft)."""
    pressure_alt = station_elev_ft + ((29.92 - altimeter_inhg) * 1000)
    isa_temp_c   = 15.0 - (0.00198 * pressure_alt)
    density_alt  = pressure_alt + (120 * (temp_c - isa_temp_c))
    return int(round(pressure_alt)), int(round(density_alt))

def calc_rh(temp_c, dew_c):
    """Magnus formula relative humidity (%)."""
    if temp_c is None or dew_c is None:
        return None
    a, b = 17.625, 243.04
    rh = 100 * ((a * dew_c / (b + dew_c)) - (a * temp_c / (b + temp_c)))
    # Equivalent, simpler approximation
    rh = 100 - (5 * (temp_c - dew_c))
    return max(0, min(100, round(rh)))

def parse_nws_properties(props):
    timestamp = props.get('timestamp')
    if not timestamp: return None, None, None, None
    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
    time_str = dt.strftime("%H:%MZ")
    try:
        temp_c = float(props.get('temperature', {}).get('value'))
        dew_c  = float(props.get('dewpoint',    {}).get('value'))
    except (TypeError, ValueError): temp_c, dew_c = None, None
    wdir     = props.get('windDirection', {}).get('value')
    wspd_kmh = props.get('windSpeed',     {}).get('value')
    wdir_str = f"{int(wdir):03d}" if wdir is not None else "VRB"
    wspd_kts = int(round(wspd_kmh / 1.852)) if wspd_kmh is not None else 0
    wind_str = f"{wdir_str}@{wspd_kts}kt"
    vis_m    = props.get('visibility', {}).get('value')
    vis_sm   = round(vis_m / 1609.34, 1) if vis_m is not None else "M"
    clouds_str = ""
    cloud_layers = props.get('cloudLayers') or []
    if cloud_layers:
        layer_strs = []
        for layer in cloud_layers:
            amt      = layer.get('amount', '---')
            base_dict = layer.get('base')
            base_m   = base_dict.get('value') if isinstance(base_dict, dict) else None
            if base_m is not None and amt not in ["CLR", "SKC"]:
                base_ft   = base_m * 3.28084
                base_hnds = int(round(base_ft / 100))
                layer_strs.append(f"{amt}{base_hnds:03d}")
            else:
                layer_strs.append(amt)
        clouds_str = " ".join(layer_strs)
    if not clouds_str:
        desc = props.get('textDescription', '')
        if desc and "Clear" in desc: clouds_str = "CLR"
        else: clouds_str = "M"
    temp_str   = f"{int(temp_c)}"  if temp_c is not None else "M"
    dew_str    = f"{int(dew_c)}"   if dew_c  is not None else "M"
    pres_pa    = props.get('barometricPressure', {}).get('value')
    pres_inhg  = round(pres_pa / 3386.389, 2) if pres_pa is not None else "M"
    formatted_str = f"({time_str}) | Wind: {wind_str} | Vis: {vis_sm}SM | Sky: {clouds_str} | Temp/Dew: {temp_str}/{dew_str}°C | Alt: {pres_inhg} inHg"
    return formatted_str, timestamp, temp_c, dew_c

def get_5min_asos():
    try:
        url      = "https://api.weather.gov/stations/KBHM/observations?limit=10"
        response = requests.get(url, headers=NWS_HEADERS, timeout=5)
        if response.status_code == 200:
            features = response.json().get('features', [])
            if features:
                props = features[0]['properties']
                raw   = props.get('rawMessage')
                formatted_str, timestamp, temp_c, dew_c = parse_nws_properties(props)
                if formatted_str:
                    final_raw = f"BHM 5-MIN ({timestamp[11:16]}Z) | {raw}" if raw else f"BHM 5-MIN {formatted_str}"
                    # Also grab altimeter for density-alt
                    pres_pa   = props.get('barometricPressure', {}).get('value')
                    altimeter = round(pres_pa / 3386.389, 2) if pres_pa is not None else None
                    return final_raw, timestamp, temp_c, dew_c, altimeter, None
        return None, None, None, None, None, f"HTTP {response.status_code}"
    except Exception as e:
        return None, None, None, None, None, f"Error: {str(e)}"

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
                    props         = ob['properties']
                    raw           = props.get('rawMessage')
                    formatted_str, ts, _, _ = parse_nws_properties(props)
                    if formatted_str:
                        parsed.append(f"({ts[11:16]}Z) | {raw}" if raw else formatted_str)
                data[stn] = parsed
            else:
                data[stn] = [f"API Error: HTTP {res.status_code}"]
        except:
            data[stn] = ["Connection Error"]
    return data

def get_awc_data():
    try:
        url      = "https://aviationweather.gov/api/data/metar?ids=KBHM&format=json&hours=6"
        response = requests.get(url, timeout=5)
        if response.status_code == 200: return response.json()
        return None
    except: return None

def get_taf_data():
    try:
        url      = "https://aviationweather.gov/api/data/taf?ids=KBHM&format=json"
        response = requests.get(url, timeout=5)
        if response.status_code == 200 and len(response.json()) > 0:
            return response.json()[0].get('rawTAF', 'TAF currently unavailable.')
        return "TAF currently unavailable."
    except: return "Error fetching TAF."

def extract_vis_and_cig(metar_string):
    vis_val, cig_val = 10.0, 10000
    if "Error" in metar_string or "No recent" in metar_string or not metar_string:
        return vis_val, cig_val
    vis_match = re.search(r'\s(M?P?\d+/?\d*\s?\d*/?\d*)SM', metar_string)
    if vis_match:
        vis_str = vis_match.group(1).replace('P', '').replace('M', '').strip()
        try:
            if " " in vis_str:
                whole, frac = vis_str.split(" "); num, den = frac.split("/")
                vis_val = float(whole) + (float(num) / float(den))
            elif "/" in vis_str:
                num, den = vis_str.split("/"); vis_val = float(num) / float(den)
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

# ── METAR DECODER ─────────────────────────────────────────────────────────────
WX_CODES = {
    "RA":"Rain","SN":"Snow","DZ":"Drizzle","GR":"Hail (≥1/4\")","GS":"Small Hail (<1/4\")",
    "PL":"Ice Pellets","IC":"Ice Crystals","UP":"Unknown Precip","FG":"Fog","BR":"Mist",
    "HZ":"Haze","FU":"Smoke","DU":"Dust","SA":"Sand","VA":"Volcanic Ash",
    "SQ":"Squall","FC":"Funnel Cloud","+FC":"Tornado/Waterspout","PO":"Dust/Sand Whirls",
    "SS":"Sandstorm","DS":"Duststorm","TS":"Thunderstorm","SH":"Shower",
    "FZ":"Freezing","MI":"Shallow","BC":"Patchy","PR":"Partial","DR":"Low Drifting",
    "BL":"Blowing","TSRA":"Thunderstorm w/ Rain","TSSN":"Thunderstorm w/ Snow",
    "TSPL":"Thunderstorm w/ Ice Pellets","TSGR":"Thunderstorm w/ Hail",
    "SHRA":"Rain Shower","SHSN":"Snow Shower","SHPL":"Ice Pellet Shower",
    "FZRA":"Freezing Rain","FZDZ":"Freezing Drizzle","FZFG":"Freezing Fog",
    "BLSN":"Blowing Snow","DRSN":"Drifting Snow","RASN":"Rain and Snow"
}
SKY_CODES = {"SKC":"Sky Clear","CLR":"Clear","FEW":"Few (1-2 oktas)","SCT":"Scattered (3-4 oktas)","BKN":"Broken (5-7 oktas)","OVC":"Overcast (8 oktas)","VV":"Vertical Visibility / Sky Obscured"}

def decode_metar(raw):
    raw   = raw.strip()
    parts = raw.split()
    rows  = []
    i     = 0

    def add(token, label, explanation):
        rows.append({"Token": f"`{token}`", "Element": label, "Plain-English Meaning": explanation})

    # Station ID
    if i < len(parts) and re.match(r'^[A-Z]{4}$', parts[i]):
        add(parts[i], "Station ID", f"ICAO identifier for the observing station.")
        i += 1

    # AUTO / COR
    if i < len(parts) and parts[i] in ("AUTO", "COR", "RTD"):
        tags = {"AUTO": "Fully automated observation — no human augmentation.", "COR": "Correction to a previously transmitted observation.", "RTD": "Routine delayed observation."}
        add(parts[i], "Modifier", tags.get(parts[i], parts[i]))
        i += 1

    # Date/Time  DDHHMMz
    if i < len(parts) and re.match(r'^\d{6}Z$', parts[i]):
        t = parts[i]
        add(t, "Date/Time (UTC)", f"Day {t[0:2]}, Time {t[2:4]}:{t[4:6]} UTC (Zulu).")
        i += 1

    # Wind
    if i < len(parts):
        m = re.match(r'^(VRB|\d{3})(\d{2,3})(G(\d{2,3}))?KT$', parts[i])
        if m:
            direction = "Variable" if m.group(1) == "VRB" else f"{m.group(1)}°"
            speed     = m.group(2)
            gust_part = f", gusting to {m.group(4)} kt" if m.group(4) else ""
            add(parts[i], "Wind", f"From {direction} at {speed} knots{gust_part}.")
            i += 1
        # Variable wind direction range  e.g. 180V270
        if i < len(parts) and re.match(r'^\d{3}V\d{3}$', parts[i]):
            add(parts[i], "Variable Wind Range", f"Wind direction variable between {parts[i][:3]}° and {parts[i][4:]}°.")
            i += 1

    # Visibility
    if i < len(parts):
        vis_token = parts[i]
        # Look ahead for fractional  e.g. "1 1/2SM"
        if i + 1 < len(parts) and re.match(r'^\d+/\d+SM$', parts[i+1]) and re.match(r'^\d+$', parts[i]):
            combined = f"{parts[i]} {parts[i+1]}"
            num_str  = parts[i]; frac = parts[i+1].replace('SM','')
            n, d     = frac.split('/'); val = float(num_str) + float(n)/float(d)
            add(combined, "Visibility", f"{val} statute miles.")
            i += 2
        elif re.match(r'^(M|P)?\d+(/\d+)?SM$', vis_token):
            prefix = "Less than " if vis_token.startswith('M') else ("Greater than " if vis_token.startswith('P') else "")
            num_s  = vis_token.replace('M','').replace('P','').replace('SM','')
            try:
                if '/' in num_s: n,d = num_s.split('/'); val = float(n)/float(d)
                else: val = float(num_s)
                add(vis_token, "Visibility", f"{prefix}{val} statute miles.")
            except:
                add(vis_token, "Visibility", vis_token)
            i += 1

    # RVR  R28L/2000FT or R28L/M0600FT
    while i < len(parts) and re.match(r'^R\d+[LCR]?/', parts[i]):
        rvr = parts[i]
        rwy = re.match(r'^R(\d+[LCR]?)/', rvr).group(1)
        val_part = rvr.split('/')[1]
        prefix   = "≤ " if val_part.startswith('M') else (">= " if val_part.startswith('P') else "")
        ft_val   = re.sub(r'[MPUF]+','', val_part.replace('FT',''))
        add(rvr, "RVR", f"Runway {rwy} Visual Range: {prefix}{ft_val} ft.")
        i += 1

    # Present Weather
    while i < len(parts):
        m = re.match(r'^(\+|-|VC)?(TS|SH|FZ|MI|BC|PR|DR|BL)?([A-Z]{2,4})$', parts[i])
        if m and (parts[i] in WX_CODES or m.group(3) in WX_CODES or parts[i].lstrip('+-') in WX_CODES):
            intensity = {"+" : "Heavy ", "-" : "Light ", "VC": "In the Vicinity — "}.get(m.group(1), "Moderate ")
            base_code = parts[i].lstrip('+-').replace('VC','')
            desc      = WX_CODES.get(parts[i], WX_CODES.get(base_code, parts[i]))
            add(parts[i], "Present Weather", f"{intensity}{desc}.")
            i += 1
        else:
            break

    # Sky condition
    while i < len(parts):
        m = re.match(r'^(SKC|CLR|FEW|SCT|BKN|OVC|VV)(\d{3})?(CB|TCU)?$', parts[i])
        if m:
            code  = m.group(1); ht = m.group(2); conv = m.group(3) or ""
            ht_ft = f" at {int(ht)*100:,} ft AGL" if ht else ""
            conv_s= " with Cumulonimbus" if conv=="CB" else (" with Towering Cumulus" if conv=="TCU" else "")
            add(parts[i], "Sky Condition", f"{SKY_CODES.get(code, code)}{ht_ft}{conv_s}.")
            i += 1
        else:
            break

    # Temp / Dewpoint  e.g. 25/18 or M02/M05
    if i < len(parts) and re.match(r'^M?\d+/M?\d+$', parts[i]):
        td = parts[i].split('/')
        def conv(s): return -int(s[1:]) if s.startswith('M') else int(s)
        tc = conv(td[0]); dc = conv(td[1])
        tf = round(tc * 9/5 + 32); df = round(dc * 9/5 + 32)
        spread = tc - dc
        add(parts[i], "Temp / Dewpoint", f"Temperature {tc}°C ({tf}°F), Dewpoint {dc}°C ({df}°F). Spread: {spread}°C.")
        i += 1

    # Altimeter  A2992
    if i < len(parts) and re.match(r'^A\d{4}$', parts[i]):
        inhg = int(parts[i][1:]) / 100
        add(parts[i], "Altimeter Setting", f"{inhg:.2f} inHg — set all aircraft altimeters to this value.")
        i += 1

    # Remarks section
    if i < len(parts) and parts[i] == "RMK":
        add("RMK", "Remarks Begin", "Everything that follows is supplemental encoded remarks.")
        i += 1
        rmk_text = " ".join(parts[i:])

        # AO1 / AO2
        if "AO1" in rmk_text: rows.append({"Token":"`AO1`","Element":"ASOS Type","Plain-English Meaning":"Automated station — no precipitation discriminator (cannot distinguish liquid from frozen precip)."})
        if "AO2" in rmk_text: rows.append({"Token":"`AO2`","Element":"ASOS Type","Plain-English Meaning":"Automated station WITH precipitation discriminator (can distinguish liquid from frozen precip)."})

        # SLP
        slp_m = re.search(r'SLP(\d{3})', rmk_text)
        if slp_m:
            slp_raw = int(slp_m.group(1))
            slp_mb  = (1000 + slp_raw/10) if slp_raw < 500 else (900 + slp_raw/10)
            rows.append({"Token":f"`SLP{slp_m.group(1)}`","Element":"Sea-Level Pressure",
                         "Plain-English Meaning":f"{slp_mb:.1f} mb / hPa sea-level pressure."})

        # PRESRR / PRESFR
        if "PRESRR" in rmk_text: rows.append({"Token":"`PRESRR`","Element":"Pressure","Plain-English Meaning":"Pressure Rising Rapidly (≥0.06 inHg in past hour)."})
        if "PRESFR" in rmk_text: rows.append({"Token":"`PRESFR`","Element":"Pressure","Plain-English Meaning":"Pressure Falling Rapidly (≥0.06 inHg in past hour)."})

        # Peak wind
        pk_m = re.search(r'PK WND (\d{3})(\d{2,3})/(\d{2,4})', rmk_text)
        if pk_m:
            rows.append({"Token":f"`PK WND {pk_m.group(0).split()[-1]}`","Element":"Peak Wind",
                         "Plain-English Meaning":f"Peak wind from {pk_m.group(1)}° at {pk_m.group(2)} kt, occurred at :{pk_m.group(3)[-2:]} past the hour."})

        # WSHFT
        ws_m = re.search(r'WSHFT (\d+)( FROPA)?', rmk_text)
        if ws_m:
            fropa = " — associated with a frontal passage." if ws_m.group(2) else "."
            rows.append({"Token":f"`WSHFT {ws_m.group(1)}{ws_m.group(2) or ''}`","Element":"Wind Shift",
                         "Plain-English Meaning":f"Wind shift occurred at :{ws_m.group(1)} past the hour{fropa}"})

        # T-group  T00250011
        tg = re.search(r'T(\d)(\d{3})(\d)(\d{3})', rmk_text)
        if tg:
            def tconv(sign, val): t = int(val)/10; return (-t if sign=='1' else t)
            tc2 = tconv(tg.group(1), tg.group(2)); dc2 = tconv(tg.group(3), tg.group(4))
            rows.append({"Token":f"`T{tg.group(0)[1:]}`","Element":"Hourly Temp/Dew (tenths)",
                         "Plain-English Meaning":f"Precise temperature {tc2:.1f}°C, dewpoint {dc2:.1f}°C."})

        # Precip accumulation  P0012
        p1h = re.search(r'\bP(\d{4})\b', rmk_text)
        if p1h:
            inches = int(p1h.group(1))/100
            rows.append({"Token":f"`P{p1h.group(1)}`","Element":"Hourly Precip",
                         "Plain-English Meaning":f"{inches:.2f} inches of precipitation in the past hour."})

        # Lightning
        ltg_m = re.search(r'(OCNL|FRQ|CONS) LTG([A-Z]*) ([A-Z]+)', rmk_text)
        if ltg_m:
            freq_map = {"OCNL":"Occasional (1-5 per min)","FRQ":"Frequent (6-15 per min)","CONS":"Continuous (>15 per min)"}
            rows.append({"Token":f"`{ltg_m.group(0)}`","Element":"Lightning",
                         "Plain-English Meaning":f"{freq_map.get(ltg_m.group(1), ltg_m.group(1))} lightning of type(s) {ltg_m.group(2) or 'unspecified'} in the {ltg_m.group(3)} direction."})

        # TS location
        ts_m = re.search(r'TS (OHD|VC|DSNT|ALQDS|[NESW]+)', rmk_text)
        if ts_m:
            loc_map = {"OHD":"Overhead","VC":"In the Vicinity (5-10 mi)","DSNT":"Distant (>10 mi)","ALQDS":"All Quadrants"}
            rows.append({"Token":f"`TS {ts_m.group(1)}`","Element":"Thunderstorm",
                         "Plain-English Meaning":f"Thunderstorm {loc_map.get(ts_m.group(1), ts_m.group(1))}."})

        # TORNADO / FUNNEL CLOUD
        if "TORNADO" in rmk_text: rows.append({"Token":"`TORNADO`","Element":"Tornadic Activity","Plain-English Meaning":"Tornado reported — immediate safety action required."})
        if "FUNNEL CLOUD" in rmk_text: rows.append({"Token":"`FUNNEL CLOUD`","Element":"Tornadic Activity","Plain-English Meaning":"Funnel cloud observed but not reaching the ground."})

        # Virga
        if "VIRGA" in rmk_text: rows.append({"Token":"`VIRGA`","Element":"Virga","Plain-English Meaning":"Precipitation falling from clouds that evaporates before reaching the surface."})

        # TSNO
        if "TSNO" in rmk_text: rows.append({"Token":"`TSNO`","Element":"TS Sensor","Plain-English Meaning":"ASOS thunderstorm sensor (ALDARS/Lightning Sensor) is inoperative."})

        # RVRNO
        if "RVRNO" in rmk_text: rows.append({"Token":"`RVRNO`","Element":"RVR","Plain-English Meaning":"RVR system is inoperative."})

        # FROIN
        if "FROIN" in rmk_text: rows.append({"Token":"`FROIN`","Element":"Ice/Frost","Plain-English Meaning":"Frost/ice is forming on the instrument shelter (freezing fog)."})

        i = len(parts)  # consumed all

    return rows

# ── COMM CHECK ────────────────────────────────────────────────────────────────
st.markdown("### 📡 System Comm Status (5-Min Early Warning)")
latest_raw, latest_ts, live_temp_c, live_dew_c, live_altimeter, diag_err = get_5min_asos()

if latest_raw and latest_ts:
    try:
        ob_time     = datetime.fromisoformat(latest_ts.replace('Z', '+00:00'))
        now_utc     = datetime.now(timezone.utc)
        age_minutes = (now_utc - ob_time).total_seconds() / 60
        col_a, col_b = st.columns([2, 1])
        with col_a: st.code(f"{latest_raw}", language="bash")
        with col_b:
            if age_minutes > 45: st.error(f"🚨 **COMM WARNING:** Ping is **{int(age_minutes)} mins old!** Check long-line.")
            else: st.success(f"✅ **Comms Good:** Latency is **{int(age_minutes)}** mins.")
    except: st.warning("Could not calculate age.")
else:
    st.warning(f"⚠️ 5-minute network ping unavailable. Diagnostic code: {diag_err}")

# ── FLIGHT CATEGORY BANNER ────────────────────────────────────────────────────
awc_data_for_cat = get_awc_data()
banner_metar     = awc_data_for_cat[0].get('rawOb', '') if awc_data_for_cat else ""
live_vis_cat, live_cig_cat = extract_vis_and_cig(banner_metar)
flight_cat, fg_hex, bg_hex = get_flight_cat(live_vis_cat, live_cig_cat)

cat_desc = {
    "VFR":  "Visual Flight Rules — Ceiling >3,000 ft & Vis >5 SM",
    "MVFR": "Marginal VFR — Ceiling 1,000–3,000 ft and/or Vis 3–5 SM",
    "IFR":  "Instrument Flight Rules — Ceiling 500–999 ft and/or Vis 1–2 SM",
    "LIFR": "Low IFR — Ceiling <500 ft and/or Vis <1 SM",
}
st.markdown(
    f'<div class="flight-cat-banner" style="background-color:{bg_hex}; color:{fg_hex};">'
    f'✈️ KBHM: {flight_cat} — <span style="font-size:14px;font-weight:normal;">{cat_desc[flight_cat]}</span>'
    f'</div>',
    unsafe_allow_html=True
)

# RVR awareness warning
if live_vis_cat < 1.0:
    st.error(
        "🚨 **LOW VISIBILITY — RVR PROTOCOL ACTIVE**\n\n"
        "• Verify RVR sensor(s) are reporting on all active runways.\n"
        "• Encode RVR in METAR immediately below visibility (R##L/XXXXFT).\n"
        "• Coordinate with ATCT — check if runway change or NOTAM is needed.\n"
        "• If RVR inoperative, add **RVRNO** to remarks."
    )
elif live_vis_cat < 3.0:
    st.warning("⚠️ **Visibility below 3 SM — Monitor for RVR sensor activation and SPECI criteria.**")

st.divider()

# ── TOP: OBSERVATIONS & RADAR ─────────────────────────────────────────────────
top_col1, top_col2 = st.columns([1, 1])

with top_col1:
    tab_local, tab_regional = st.tabs(["📍 KBHM Transmitted", "🌍 Regional 5-Min (50-mi)"])

    with tab_local:
        awc_data    = awc_data_for_cat  # reuse fetch
        recent_metars = [obs.get('rawOb', 'No raw string') for obs in awc_data[:6]] if awc_data else ["No recent METARs found."]
        latest_metar  = recent_metars[0] if recent_metars else ""
        live_vis, live_cig = extract_vis_and_cig(latest_metar)

        if "No recent" not in latest_metar:
            for i, metar in enumerate(recent_metars):
                if i == 0: st.error(f"**LATEST:** `{metar}`")
                elif i == 1: st.warning(f"`{metar}`")
                else: st.info(f"`{metar}`")
        else:
            st.warning("Could not load AWC METARs.")

        st.markdown("---")
        st.markdown("#### ✈️ KBHM Current TAF")
        taf_string = get_taf_data()
        st.info(f"`{taf_string}`")

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
    st.image("https://radar.weather.gov/ridge/standard/KBMX_loop.gif",
             caption="Live NWS Birmingham (BMX) Radar Loop", use_container_width=True)

st.divider()

# ── CALCULATORS, CONTACTS & METAR DECODER ────────────────────────────────────
st.subheader("🧮 JO 7900.5E Calculators & SOPs")
calc_tab, cont_tab, decoder_tab = st.tabs(["Calculators", "📞 Contacts & SOPs", "🔍 METAR Decoder"])

with calc_tab:
    # Row 1 — SPECI & Convective base
    r1c1, r1c2, r1c3, r1c4 = st.columns(4)

    with r1c1:
        st.markdown("**🌫️ Visibility SPECI**")
        old_vis    = st.number_input("Prev Vis (SM)", min_value=0.0, value=10.0, step=0.25, key="vis_old")
        new_vis    = st.number_input("Cur Vis (SM)",  min_value=0.0, value=float(live_vis), step=0.25, key="vis_new")
        vis_speci, vis_trigger = check_speci(old_vis, new_vis, vis_thresholds)
        if old_vis != new_vis:
            if vis_speci: st.error(f"🚨 **SPECI:** Crossed {vis_trigger} SM.")
            else: st.success("✅ No SPECI required.")

    with r1c2:
        st.markdown("**☁️ Ceiling SPECI**")
        old_cig    = st.number_input("Prev Ceiling (Ft)", min_value=0, value=5000,         step=100, key="cig_old")
        new_cig    = st.number_input("Cur Ceiling (Ft)",  min_value=0, value=int(live_cig), step=100, key="cig_new")
        cig_speci, cig_trigger = check_speci(old_cig, new_cig, cig_thresholds)
        if old_cig != new_cig:
            if cig_speci: st.error(f"🚨 **SPECI:** Crossed {cig_trigger} FT.")
            else: st.success("✅ No SPECI required.")

    with r1c3:
        st.markdown("**☁️ Convective Cloud Base**")
        if live_temp_c is not None and live_dew_c is not None:
            t_c_r = round(live_temp_c); d_c_r = round(live_dew_c)
            t_f   = (t_c_r * 9/5) + 32; d_f = (d_c_r * 9/5) + 32
            spread_f = t_f - d_f
            ccl_agl  = int(round((spread_f * 230) / 100.0)) * 100
            rh_val   = calc_rh(live_temp_c, live_dew_c)
            st.info(f"**Spread:** {int(spread_f)}°F ({t_c_r}C/{d_c_r}C)")
            st.success(f"**Est. Cloud Base:** {ccl_agl:,} ft AGL")
            if rh_val is not None:
                rh_color = "🟢" if rh_val >= 70 else ("🟡" if rh_val >= 40 else "🔴")
                st.metric("Relative Humidity", f"{rh_val}%", help="Higher RH = deeper boundary layer moisture. ≥70% supports fog/stratus development.")
                if rh_val >= 90: st.warning("⚠️ RH ≥ 90% — fog/low stratus development possible.")
        else:
            st.warning("Awaiting live T/Td data...")

    with r1c4:
        st.markdown("**⚡ Flash-to-Bang (Lightning)**")
        st.caption("Distance Rules: **0-5mi** = OHD | **5-10mi** = VC | **10-30mi** = DSNT")
        sec_delay = st.number_input("Seconds between Flash and Thunder:", min_value=0, value=0, step=1)
        if sec_delay > 0:
            miles = round(sec_delay / 5.0, 1)
            if miles <= 5:  st.error(f"**{miles} Miles → TS OHD**")
            elif miles <= 10: st.warning(f"**{miles} Miles → TS VC**")
            else: st.success(f"**{miles} Miles → TS DSNT**")
        else:
            st.caption("Divide seconds by 5 to get miles.")

    st.markdown("---")

    # Row 2 — Density Altitude
    st.markdown("**✈️ Density Altitude Calculator**")
    st.caption("Critical for high-temp summer operations at BHM (elev 644 ft MSL). DA affects aircraft performance advisories to ATC.")

    da_c1, da_c2, da_c3 = st.columns(3)

    # Pre-fill with live data where available
    da_temp_default = round(live_temp_c) if live_temp_c is not None else 25
    da_alt_default  = float(live_altimeter) if live_altimeter is not None else 29.92

    with da_c1:
        da_temp_c   = st.number_input("OAT (°C)", value=da_temp_default, min_value=-60, max_value=60, step=1, key="da_temp")
        da_temp_f   = round(da_temp_c * 9/5 + 32)
        st.caption(f"= {da_temp_f}°F")
    with da_c2:
        da_altimeter = st.number_input("Altimeter (inHg)", value=da_alt_default, min_value=27.0, max_value=31.5, step=0.01, format="%.2f", key="da_alt")
    with da_c3:
        da_elev      = st.number_input("Station Elevation (ft MSL)", value=644, min_value=0, max_value=10000, step=10, key="da_elev")

    pa, da = calc_density_altitude(da_temp_c, da_altimeter, da_elev)
    da_delta = da - da_elev
    da_col1, da_col2, da_col3 = st.columns(3)
    with da_col1: st.metric("Pressure Altitude", f"{pa:,} ft")
    with da_col2: st.metric("Density Altitude",  f"{da:,} ft", delta=f"{da_delta:+,} ft above field")
    with da_col3:
        if da > 5000:
            st.error(f"🚨 **HIGH DA** — Significant aircraft performance degradation. Advise ATCT.")
        elif da > 3000:
            st.warning(f"⚠️ Elevated DA — Aircraft may require longer takeoff rolls.")
        else:
            st.success(f"✅ DA within normal range for BHM operations.")

with cont_tab:
    st.markdown("### 📞 BHM Emergency Contacts & IT")
    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        st.markdown("**FAA / ATC**\n* BHM ATCT CAB: `205-769-3914`\n* BHM TRACON: `205-769-3907`\n* Tech Ops: `205-769-3950`\n* NWS Office: `205-621-5650`")
    with col_c2:
        st.markdown("**Maintenance / IT**\n* Jeff Short (WDI): `641-923-6043`\n* BHM IT (Free WiFi): `205-599-0700`\n* Facilities (Mathew): `205-595-0595`\n* BHM Voice: `205-591-6172`")
    with col_c3:
        st.markdown("**ASOS OUTAGES**\n* AOMC: `1-800-242-8194` or `8895`\n* NEMC (Comms): `1-855-322-6362` *(→ ATL → #3)*\n* ARTCC Longline: `1-770-210-7960` *(cell only)*")

with decoder_tab:
    st.markdown("### 🔍 METAR Plain-English Decoder")
    st.caption(
        "Paste any raw METAR below. Each element is decoded line-by-line with its JO 7900.5E meaning. "
        "Great for training new and part-time observers."
    )
    default_ex = "KBHM 181453Z 18012G22KT 10SM FEW045 BKN250 28/18 A3002 RMK AO2 SLP156 T02830178 PK WND 19028/1421 WSHFT 32 FROPA"
    metar_input = st.text_area("Paste METAR here:", value=default_ex, height=80)

    if st.button("🔍 Decode METAR"):
        if metar_input.strip():
            decoded_rows = decode_metar(metar_input.strip())
            if decoded_rows:
                import pandas as pd
                df = pd.DataFrame(decoded_rows)
                st.dataframe(df, use_container_width=True, hide_index=True,
                             column_config={
                                 "Token":                  st.column_config.TextColumn(width="small"),
                                 "Element":                st.column_config.TextColumn(width="medium"),
                                 "Plain-English Meaning":  st.column_config.TextColumn(width="large"),
                             })
                st.caption(f"Decoded {len(decoded_rows)} elements from the METAR. Elements not recognized are silently skipped (e.g., raw hourly values).")
            else:
                st.warning("No recognizable METAR elements found. Check the format.")
        else:
            st.warning("Please paste a METAR string above.")

st.divider()

# ── REMARKS (RMK) BUILDER ─────────────────────────────────────────────────────
st.subheader("📝 Remarks (RMK) Builder (A-Z Strict Order)")
tab_svr, tab_wind, tab_ts, tab_precip = st.tabs(["🌪️ Severe Wx", "💨 Wind/Pressure", "🌩️ TS & Lightning", "🌧️ Precip/Vis/Hail"])
rmks = {letter: "" for letter in "ABCDEFGHIJKLMNOPQRSTUVW"}

with tab_svr:
    col_a, col_b = st.columns(2)
    with col_a:
        has_torn = st.checkbox("Tornadic Activity")
        if has_torn:
            st.error("🚨 MAIN OBS REMINDER: Add `+FC` or `FC` to Present WX.")
            torn_type = st.selectbox("Type:", ["TORNADO", "FUNNEL CLOUD", "WATERSPOUT"])
            torn_b, torn_e = st.text_input("Begin Time (Min):", ""), st.text_input("End Time (Min):", "")
            torn_loc = st.selectbox("Location:", ["", "ALQDS", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])
            torn_mov = st.selectbox("Moving:", ["", "N", "NE", "E", "SE", "S", "SW", "W", "NW"])
            t_str    = f"{torn_type}" + (f" B{torn_b}" if torn_b else "") + (f" E{torn_e}" if torn_e else "") + (f" {torn_loc}" if torn_loc else "") + (f" MOV {torn_mov}" if torn_mov else "")
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
            pk_min = st.number_input("Minute (past hour)", min_value=0, max_value=59, step=1, value=15)
            # FIX: If peak occurred in the PREVIOUS hour, include the hour in the time field
            pk_prev_hour = st.checkbox("Peak occurred in PREVIOUS hour?", help="JO 7900.5E: If peak wind occurred before the current clock hour, prepend the hour (HHMM).")
            if pk_prev_hour:
                prev_hour  = (now_ct.hour - 1) % 24
                pk_time_str = f"{prev_hour:02d}{pk_min:02d}"
                st.caption(f"Time field will encode as: **{pk_time_str}** (hour {prev_hour:02d}, minute {pk_min:02d})")
            else:
                pk_time_str = f"{pk_min:02d}"
            rmks['C'] = f"PK WND {pk_dir:03d}{pk_spd}/{pk_time_str}"
    with col_w2:
        has_wshft = st.checkbox("Wind Shift")
        if has_wshft:
            wshft_time  = st.number_input("Shift Time (Min)", min_value=0, max_value=59, step=1, value=15)
            fropa_check = st.checkbox("FROPA (Frontal Passage)")
            rmks['D']   = f"WSHFT {wshft_time:02d}" + (" FROPA" if fropa_check else "")
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
            ltg_loc   = st.selectbox("LTG Location:", ["ALQDS","OHD","VC","DSNT","N","NE","E","SE","S","SW","W","NW"])
            rmks['H'] = f"{ltg_freq} LTG{''.join(ltg_types)} {ltg_loc}"
    with col_ts2:
        has_ts = st.checkbox("Thunderstorm Active")
        if has_ts:
            st.warning("🚨 **TS REMINDER:** Put `TS` in Pres WX | Add `CB` to Sky | Turn ALDARS to `MAN`")
            ts_loc = st.selectbox("TS Location:", ["OHD","VC","DSNT","ALQDS","N","NE","E","SE","S","SW","W","NW"])
            ts_mov = st.selectbox("TS Moving:", ["Unknown","N","NE","E","SE","S","SW","W","NW"])
            rmks['K'] = f"TS {ts_loc}" + (f" MOV {ts_mov}" if ts_mov != "Unknown" else "")

with tab_precip:
    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    with col_p1:
        st.markdown("**🌧️ Precipitation**")
        has_precip = st.checkbox("Precip Begin/End")
        if has_precip:
            p_type = st.selectbox("Precip Type:", ["RA", "SN", "DZ", "UP"])
            p_b    = st.text_input("B (Min past HR):", "")
            p_e    = st.text_input("E (Min past HR):", "")
            rmks['I'] = f"{p_type}" + (f"B{p_b}" if p_b else "") + (f"E{p_e}" if p_e else "")
    with col_p2:
        st.markdown("**🧊 Hail**")
        has_hail = st.checkbox("Hail (GR/GS)")
        if has_hail:
            st.error("🚨 REMINDER: `GR` (≥1/4 in) or `GS` (<1/4 in).")
            rmks['L'] = f"GR {st.text_input('Hail Size:', '1/4')}"
    with col_p3:
        st.markdown("**🌫️ Virga**")
        has_virga = st.checkbox("VIRGA")
        if has_virga:
            virga_loc = st.selectbox("Virga Loc:", ["ALQDS","N","NE","E","SE","S","SW","W","NW"])
            rmks['M'] = "VIRGA ALQDS" if virga_loc == "ALQDS" else f"VIRGA {virga_loc}"
    with col_p4:
        st.markdown("**👁️ Visibility Remarks**")
        has_sector_vis = st.checkbox("Sector Vis (RMK G)")
        if has_sector_vis:
            sec_dir = st.selectbox("Sector:", ["N","NE","E","SE","S","SW","W","NW"])
            sec_vis = st.text_input("Vis (e.g. 1 1/2):", "1")
            rmks['G'] = f"VIS {sec_dir} {sec_vis}"
        has_vrb_vis = st.checkbox("Variable Vis (RMK F)")
        if has_vrb_vis:
            vrb_min = st.text_input("Min Vis:", "1/2")
            vrb_max = st.text_input("Max Vis:", "2")
            rmks['F'] = f"VIS {vrb_min}V{vrb_max}"

st.markdown("---")
final_remarks = [rmks[key] for key in sorted(rmks.keys()) if rmks[key] != ""]
if final_remarks:
    st.success("**Final JO 7900.5E Remark String (Correct Order):**")
    st.code("RMK " + " ".join(final_remarks), language="markdown")

st.divider()

# ── JO 7900.5E PDF VIEWER ─────────────────────────────────────────────────────
st.subheader("📚 JO 7900.5E Reference Manual")
st.markdown("Search the official FAA manual, or enter a specific page number below to jump directly to it.")

if os.path.exists("Order_JO_7900.5E.pdf"):
    try:
        doc         = fitz.open("Order_JO_7900.5E.pdf")
        total_pages = len(doc)

        search_query = st.text_input("🔍 Search keyword (e.g., 'Freezing Drizzle', 'Tornado', 'SPECI'):")
        if search_query:
            with st.spinner(f"Scanning JO 7900.5E for '{search_query}'..."):
                results = []
                for pg in range(total_pages):
                    text = doc[pg].get_text()
                    if search_query.lower() in text.lower():
                        idx     = text.lower().find(search_query.lower())
                        start   = max(0, idx - 40)
                        snippet = text[start:min(len(text), idx + 40)].replace('\n', ' ')
                        results.append((pg, snippet))
                if results:
                    st.success(f"✅ Found {len(results)} matching pages!")
                    match_dict     = {f"Page {p+1} ( ...{snip}... )": p for p, snip in results}
                    selected_match = st.selectbox("Select a match to jump to that page:", list(match_dict.keys()))
                    if st.button("Load Search Result Page"):
                        st.session_state.pdf_page = match_dict[selected_match]
                else:
                    st.warning("No results found.")

        if 0 <= st.session_state.pdf_page < total_pages:
            st.markdown("---")
            col_p1, col_p2, col_p3 = st.columns([1, 2, 1])
            with col_p1:
                if st.button("⬅️ Previous Page") and st.session_state.pdf_page > 0:
                    st.session_state.pdf_page -= 1; st.rerun()
            with col_p2:
                jump_val = st.number_input(f"Jump to Page (1–{total_pages}):", min_value=1, max_value=total_pages, value=st.session_state.pdf_page + 1)
                if jump_val - 1 != st.session_state.pdf_page:
                    st.session_state.pdf_page = jump_val - 1; st.rerun()
            with col_p3:
                if st.button("Next Page ➡️") and st.session_state.pdf_page < total_pages - 1:
                    st.session_state.pdf_page += 1; st.rerun()
            page = doc.load_page(st.session_state.pdf_page)
            pix  = page.get_pixmap(dpi=150)
            st.image(pix.tobytes("png"), use_container_width=True)

    except Exception as e:
        st.error(f"Error reading PDF. Check requirements.txt for PyMuPDF. ({e})")
else:
    st.error("⚠️ `Order_JO_7900.5E.pdf` not found in the app folder!")
