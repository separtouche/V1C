import streamlit as st
import json
import os
import pandas as pd
import math
import base64
from datetime import datetime

# ===================== Styles =====================
GUERBET_BLUE = "#124F7A"
GUERBET_DARK = "#0D334F"
CARD_BG = "#EAF1F8"

st.set_page_config(page_title="Calculette Contraste", page_icon="💉", layout="wide")
st.markdown(f"""
<style>
.stApp {{ background-color: #F7FAFC; font-family: 'Segoe UI', sans-serif; }}
h1, h2, h3 {{ font-weight: 600; letter-spacing: -0.5px; }}
.header-banner {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  background-color: {GUERBET_BLUE};
  padding: 0.2rem 1rem;
  border-radius: 10px;
  margin-bottom: 1rem;
  height: 120px;
}}
.header-logo {{ height: 100%; width: auto; object-fit: contain; }}
.header-title {{
  color: white;
  font-size: 2rem;
  text-align: center;
  flex: 1;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-shadow: 1px 1px 2px rgba(0,0,0,0.3);
}}
.result-card {{
    background-color: {CARD_BG};
    border-radius: 12px;
    box-shadow: 0 4px 8px rgba(0,0,0,0.07);
    padding: 12px;
    text-align: center;
    transition: transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out;
    min-height: 130px;
    display: flex;
    flex-direction: column;
    justify-content: center;
}}
.result-card:hover {{
    transform: scale(1.02);
    box-shadow: 0 6px 14px rgba(0,0,0,0.12);
}}
.result-card h3 {{ margin-bottom:4px; font-size:0.95rem; }}
.result-card h1 {{ margin:0; font-size:1.5rem; }}
.param-section {{
    background: #ffffff;
    border-radius: 10px;
    padding: 16px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    margin-bottom: 12px;
}}
</style>
""", unsafe_allow_html=True)

# ===================== Config =====================
CONFIG_FILE = "iodine_config.json"
default_config = {
    "charges": {str(kv): val for kv, val in zip([80,90,100,110,120],[0.35,0.38,0.40,0.42,0.45])},
    "concentration_mg_ml": 350,
    "portal_time": 30.0,
    "arterial_time": 25.0,
    "intermediate_enabled": False,
    "intermediate_time": 28.0,
    "acquisition_start_param": 70.0,
    "auto_acquisition_by_age": True,
    "max_debit": 6.0,
    "rinçage_enabled": True,
    "rinçage_volume": 35.0,
    "rinçage_delta_debit": 0.5
}
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
    except:
        config = default_config.copy()
else:
    config = default_config.copy()

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ===================== Fonctions =====================
def calculate_bsa(weight, height):
    return math.sqrt((height * weight) / 3600)

def calculate_volume(weight, height, kv, concentration, imc, calc_mode, charges):
    kv_factors = {80: 11, 90: 13, 100: 15, 110: 16.5, 120: 18.6}
    if calc_mode == "Surface corporelle" or (calc_mode.startswith("Charge iodée sauf") and imc >= 30):
        bsa = calculate_bsa(weight, height)
        factor = kv_factors.get(kv, 15)
        volume = bsa * factor / (concentration / 1000)
    else:
        charge_iodine = float(charges.get(str(kv), 0.4))
        volume = weight * charge_iodine / (concentration / 1000)
        bsa = None
    return min(volume, 200.0), bsa

def calculate_acquisition_start(age, cfg):
    if not cfg.get("auto_acquisition_by_age", True):
        return float(cfg.get("acquisition_start_param", 70.0))
    if age < 70:
        return float(cfg.get("acquisition_start_param", 70.0))
    elif 70 <= age <= 90:
        return float(age)
    else:
        return 90.0

def adjust_injection_rate(volume, injection_time, max_debit):
    injection_rate = volume / injection_time if injection_time > 0 else 0.0
    time_adjusted = False
    if injection_rate > max_debit:
        injection_time = volume / max_debit
        injection_rate = max_debit
        time_adjusted = True
    return float(injection_rate), float(injection_time), bool(time_adjusted)

# ===================== Session init =====================
if "accepted_legal" not in st.session_state:
    st.session_state["accepted_legal"] = False

# ===================== Header =====================
def img_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

logo_path = "guerbet_logo.png"
if os.path.exists(logo_path):
    try:
        img_b64 = img_to_base64(logo_path)
        st.markdown(f"""
        <div class="header-banner">
          <img src="data:image/png;base64,{img_b64}" class="header-logo" alt="Guerbet logo" />
          <div class="header-title">Calculette de dose de produit de contraste</div>
          <div class="header-right"></div>
        </div>
        """, unsafe_allow_html=True)
    except:
        st.markdown(f"<div class='header-banner'><div class='header-title'>Calculette de dose de produit de contraste</div></div>", unsafe_allow_html=True)
else:
    st.markdown(f"<div class='header-banner'><div class='header-title'>Calculette de dose de produit de contraste</div></div>", unsafe_allow_html=True)

# ===================== Mentions légales =====================
if not st.session_state["accepted_legal"]:
    st.markdown("### Mentions légales — acceptation requise")
    st.markdown("Avant d'utiliser cet outil, vous devez accepter la mention légale et les conditions d'utilisation.")
    
    accept = st.checkbox("✅ J’accepte les mentions légales.", key="accept_checkbox")
    
    if st.button("Accepter et continuer"):
        if accept:
            st.session_state["accepted_legal"] = True
        else:
            st.warning("Vous devez cocher la case pour accepter.")
    
    st.stop()

# ===================== Onglets =====================
tab_patient, tab_params = st.tabs(["🧍 Patient", "⚙️ Paramètres"])

# ===================== Onglet Paramètres =====================
with tab_params:
    st.header("⚙️ Paramètres globaux")
    with st.expander("💊 Configuration du calcul", expanded=True):
        config["concentration_mg_ml"] = st.selectbox("Concentration (mg I/mL)", [300,320,350,370,400], index=[300,320,350,370,400].index(int(config.get("concentration_mg_ml",350))))
        config["calc_mode"] = st.selectbox("Méthode de calcul", ["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"], index=["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"].index(config.get("calc_mode","Charge iodée")))
        config["max_debit"] = st.number_input("Débit maximal autorisé (mL/s)", value=float(config.get("max_debit",6.0)), min_value=1.0, max_value=20.0, step=0.1)
    with st.expander("⏱ Temps d'injection"):
        config["portal_time"] = st.number_input("Portal (s)", value=float(config.get("portal_time",30.0)), min_value=5.0, max_value=120.0, step=1.0)
        config["arterial_time"] = st.number_input("Artériel (s)", value=float(config.get("arterial_time",25.0)), min_value=5.0, max_value=120.0, step=1.0)
        config["intermediate_enabled"] = st.checkbox("Activer temps intermédiaire", value=bool(config.get("intermediate_enabled",False)))
        if config["intermediate_enabled"]:
            config["intermediate_time"] = st.number_input("Intermédiaire (s)", value=float(config.get("intermediate_time",28.0)), min_value=5.0, max_value=120.0, step=1.0)
    with st.expander("🚰 Rinçage au NaCl"):
        config["rinçage_enabled"] = st.checkbox("Activer rinçage", value=config.get("rinçage_enabled",True))
        config["rinçage_volume"] = st.number_input("Volume de rinçage (mL)", value=float(config.get("rinçage_volume",35.0)), min_value=10.0, max_value=100.0, step=1.0)
        config["rinçage_delta_debit"] = st.number_input("Différence débit NaCl vs contraste (mL/s)", value=float(config.get("rinçage_delta_debit",0.5)), min_value=0.1, max_value=5.0, step=0.1)
    st.markdown("**Charges en iode par kV (g I/kg)**")
    df_charges = pd.DataFrame({"kV":[80,90,100,110,120],"Charge (g I/kg)":[float(config["charges"].get(str(kv),0.35)) for kv in [80,90,100,110,120]]})
    edited_df = st.data_editor(df_charges, num_rows="fixed", use_container_width=True)
    if st.button("💾 Sauvegarder les paramètres"):
        try:
            config["charges"] = {str(int(row.kV)): float(row["Charge (g I/kg)"]) for _,row in edited_df.iterrows()}
            save_config(config)
            st.success("✅ Paramètres sauvegardés avec succès !")
        except Exception as e:
            st.error(f"Erreur lors de la sauvegarde : {e}")

# ===================== Onglet Patient =====================
with tab_patient:
    st.header("🧍 Informations patient")
    col_w, col_h, col_birth = st.columns([1,1,1])
    with col_w: weight = st.select_slider("Poids (kg)", options=list(range(20,201)), value=70)
    with col_h: height = st.select_slider("Taille (cm)", options=list(range(100,221)), value=170)
    with col_birth:
        current_year = datetime.now().year
        birth_year = st.select_slider("Année de naissance", options=list(range(current_year-120,current_year+1)), value=current_year-40)
    age = current_year - birth_year
    imc = weight / ((height/100)**2)

    col_kv, col_mode_time = st.columns([1.2,2])
    with col_kv: kv_scanner = st.radio("kV du scanner", [80,90,100,110,120], index=4, horizontal=True)
    with col_mode_time:
        col_mode, col_times = st.columns([1.2,1])
        with col_mode:
            injection_modes = ["Portal","Artériel"]
            if config.get("intermediate_enabled",False): injection_modes.append("Intermédiaire")
            injection_mode = st.radio("Mode d’injection", injection_modes, horizontal=True)
        with col_times:
            acquisition_start = calculate_acquisition_start(age, config)
            if injection_mode=="Portal": base_time=float(config.get("portal_time",30.0))
            elif injection_mode=="Artériel": base_time=float(config.get("arterial_time",25.0))
            else: base_time = st.number_input("Temps intermédiaire (s)", value=float(config.get("intermediate_time",28.0)), min_value=5.0, max_value=120.0, step=1.0)
            st.markdown(f"**Temps sélectionné :** {base_time:.0f} s")
            st.markdown(f"**Départ d'acquisition :** {acquisition_start:.1f} s")
            st.markdown(f"**Concentration :** {int(config.get('concentration_mg_ml',350))} mg I/mL")

    volume, bsa = calculate_volume(weight,height,kv_scanner,float(config.get("concentration_mg_ml",350)),imc,config.get("calc_mode","Charge iodée"),config.get("charges",{}))
    injection_rate, injection_time, time_adjusted = adjust_injection_rate(volume,float(base_time),float(config.get("max_debit",6.0)))

    # ==== Trois cartes côte à côte ====
    col_contrast, col_nacl, col_rate = st.columns(3, gap="medium")
    volume_affiche = volume if config.get("rinçage_enabled", True) else volume + 15

    with col_contrast:
        st.markdown(f"""<div class="result-card"><h3>💧 Quantité de contraste conseillée</h3><h1>{volume_affiche:.1f} mL</h1></div>""", unsafe_allow_html=True)

    nacl_debit = max(0.1, injection_rate - config.get("rinçage_delta_debit",0.5))
    with col_nacl:
        if config.get("rinçage_enabled", True):
            st.markdown(f"""<div class="result-card"><h3>💧 Volume NaCl conseillé</h3><h1>{config.get('rinçage_volume',35.0):.0f} mL @ {nacl_debit:.1f} mL/s</h1></div>""", unsafe_allow_html=True)
        else:
            st.markdown(f"""<div class="result-card"><h3>💧 Volume NaCl conseillé</h3><h1>—</h1></div>""", unsafe_allow_html=True)

    with col_rate:
        st.markdown(f"""<div class="result-card"><h3>🚀 Débit conseillé</h3><h1>{injection_rate:.1f} mL/s</h1></div>""", unsafe_allow_html=True)

    # Message sur rinçage
    if config.get("rinçage_enabled", True):
        st.info(f"💧 Rinçage activé : Volume NaCl de {config.get('rinçage_volume',35.0):.0f} mL pour pousser le PdC résiduel.")
    else:
        st.info(f"⚠️ Sans rinçage, il aurait fallu injecter {volume + 15:.0f} mL de contraste total.")

    if time_adjusted:
        st.warning(f"⚠️ Le temps d’injection a été ajusté à {injection_time:.1f}s pour respecter le débit maximal de {config.get('max_debit',6.0)} mL/s.")

    st.info(f"📏 IMC : {imc:.1f}" + (f" | Surface corporelle : {bsa:.2f} m²" if bsa else ""))

    st.markdown("""<div style='background-color:#FCE8E6; color:#6B1A00; padding:10px; border-radius:8px; margin-top:15px; font-size:0.9rem;'>⚠️ <b>Avertissement :</b> Ce logiciel est un outil d’aide à la décision. Les résultats sont <b>indicatifs</b> et doivent être validés par un professionnel de santé. L’auteur, Sébastien Partouche, et Guerbet déclinent toute responsabilité en cas d’erreur ou de mauvaise utilisation.</div>""", unsafe_allow_html=True)

# Footer
st.markdown(f"""<div style='text-align:center; margin-top:20px; font-size:0.8rem; color:#666;'>
© 2025 Guerbet | Développé par <b>Sébastien Partouche</b><br>
Ce logiciel fournit des <b>propositions de valeurs</b> et ne remplace pas le jugement médical.<br>
<div style='display:inline-block; background-color:#FCE8B2; border:1px solid #F5B800; padding:8px 15px; border-radius:10px; color:#5A4500; font-weight:600; margin-top:10px;'>🧪 Version BETA TEST – Usage interne / évaluation</div>
</div>""", unsafe_allow_html=True)
