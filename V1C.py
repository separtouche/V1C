import streamlit as st
import json, os, math, base64
from datetime import datetime
import pandas as pd

# ===================== Couleurs & Styles =====================
GUERBET_BLUE = "#124F7A"
GUERBET_DARK = "#0D334F"
CARD_BG = "#EAF1F8"

st.set_page_config(page_title="Calculette Contraste", page_icon="💉", layout="wide")

st.markdown(f"""
<style>
.stApp {{ background-color:#F7FAFC; font-family:'Segoe UI',sans-serif; }}
.header-banner {{
  display:flex; align-items:center; justify-content:space-between;
  background-color:{GUERBET_BLUE}; padding:0.2rem 1rem; border-radius:10px;
  margin-bottom:1rem; height:120px;
}}
.header-logo {{ height:100%; width:auto; object-fit:contain; }}
.header-title {{
  color:white; font-size:2rem; text-align:center; flex:1; font-weight:700;
  letter-spacing:0.5px; text-shadow:1px 1px 2px rgba(0,0,0,0.3);
}}
.result-card {{
  background-color:{CARD_BG}; border-radius:14px; box-shadow:0 6px 14px rgba(0,0,0,0.1);
  padding:20px; text-align:center; height:140px; display:flex; flex-direction:column;
  justify-content:center; transition:0.2s ease-in-out;
}}
.result-card:hover {{ transform: scale(1.03); }}
.small-note {{ font-size:0.85rem; color:#333; margin-top:6px; }}
</style>
""", unsafe_allow_html=True)

# ===================== Config =====================
CONFIG_FILE = "iodine_config.json"
default_config = {
    "charges": {str(kv): val for kv, val in zip([80,90,100,110,120],[0.35,0.38,0.40,0.42,0.45])},
    "concentration_mg_ml": 350,
    "portal_time":30.0, "arterial_time":25.0, "intermediate_enabled":False, "intermediate_time":28.0,
    "acquisition_start_param":70.0, "auto_acquisition_by_age":True,
    "calc_mode":"Charge iodée sauf IMC > 30 → Surface corporelle", "max_debit":6.0
}
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE,"r") as f: config=json.load(f)
    except: config=default_config.copy()
else: config=default_config.copy()
def save_config(data):
    with open(CONFIG_FILE,"w") as f: json.dump(data,f,indent=4)

# ===================== Fonctions =====================
def calculate_bsa(w,h): return math.sqrt((h*w)/3600)
def calculate_volume(w,h,kv,conc,imc,mode,charges):
    kvf={80:11,90:13,100:15,110:16.5,120:18.6}
    if mode=="Surface corporelle" or (mode.startswith("Charge iodée sauf") and imc>=30):
        bsa=calculate_bsa(w,h); factor=kvf.get(kv,15)
        vol=bsa*factor/(conc/1000)
    else: vol=w*float(charges.get(str(kv),0.4))/(conc/1000); bsa=None
    return min(vol,200),bsa
def calculate_acq_start(age,cfg):
    if not cfg.get("auto_acquisition_by_age",True): return float(cfg.get("acquisition_start_param",70.0))
    if age<70: return float(cfg.get("acquisition_start_param",70.0))
    elif age<=90: return float(age)
    else: return 90.0
def adjust_rate(vol,time,maxd):
    rate=vol/time if time>0 else 0; adj=False
    if rate>maxd: time=vol/maxd; rate=maxd; adj=True
    return float(rate),float(time),adj

# ===================== Session =====================
if "accepted_legal" not in st.session_state: st.session_state["accepted_legal"]=False

# ===================== Header =====================
def img_to_b64(path):
    with open(path,"rb") as f: return base64.b64encode(f.read()).decode()
logo_path="guerbet_logo.png"
if os.path.exists(logo_path):
    try:
        img_b64=img_to_b64(logo_path)
        st.markdown(f"""
        <div class="header-banner">
          <img src="data:image/png;base64,{img_b64}" class="header-logo"/>
          <div class="header-title">Calculette de dose de produit de contraste</div>
          <div style="width:120px"></div>
        </div>
        """,unsafe_allow_html=True)
    except: st.markdown(f"<div class='header-banner'><div class='header-title'>Calculette de dose de produit de contraste</div></div>",unsafe_allow_html=True)
else: st.markdown(f"<div class='header-banner'><div class='header-title'>Calculette de dose de produit de contraste</div></div>",unsafe_allow_html=True)

# ===================== Acceptation légale =====================
if not st.session_state["accepted_legal"]:
    st.markdown("### Mentions légales — acceptation requise")
    st.markdown("Avant d'utiliser cet outil, vous devez accepter la mention légale et les conditions d'utilisation.")
    col1,col2,col3=st.columns([1,2,1])
    with col2:
        accept=st.checkbox("✅ J’accepte les mentions légales.")
        if st.button("Accepter et continuer"):
            if accept: st.session_state["accepted_legal"]=True; st.experimental_rerun()
            else: st.warning("Vous devez cocher la case pour accepter.")
    st.stop()

# ===================== Onglets =====================
tab_patient, tab_params=st.tabs(["🧍 Patient","⚙️ Paramètres"])

# ===================== Paramètres =====================
with tab_params:
    st.header("⚙️ Paramètres globaux")
    st.selectbox("Concentration (mg I/mL)",[300,320,350,370,400],index=[300,320,350,370,400].index(int(config.get("concentration_mg_ml",350))),disabled=False)
    st.selectbox("Méthode de calcul",["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"],
                 index=["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"].index(config.get("calc_mode","Charge iodée")))
    st.number_input("Débit max (mL/s)",value=float(config.get("max_debit",6.0)),min_value=1.0,max_value=20.0,step=0.1)
    st.number_input("Portal (s)",value=float(config.get("portal_time",30.0)),min_value=5,max_value=120,step=1.0)
    st.number_input("Artériel (s)",value=float(config.get("arterial_time",25.0)),min_value=5,max_value=120,step=1.0)
    config["intermediate_enabled"]=st.checkbox("Activer temps intermédiaire",value=config.get("intermediate_enabled",False))
    if config["intermediate_enabled"]: st.number_input("Intermédiaire (s)",value=float(config.get("intermediate_time",28.0)),min_value=5,max_value=120,step=1.0)

# ===================== Patient =====================
with tab_patient:
    st.header("🧍 Informations patient")
    weight=st.select_slider("Poids (kg)",options=list(range(20,201)),value=70)
    height=st.select_slider("Taille (cm)",options=list(range(100,221)),value=170)
    birth_year=st.select_slider("Année de naissance",options=list(range(datetime.now().year-120,datetime.now().year+1)),value=datetime.now().year-40)
    age=datetime.now().year-birth_year
    imc=weight/((height/100)**2)
    if age<18: st.warning("⚠️ Patient mineur (<18 ans) : calcul non autorisé."); st.stop()
    
    kv_col, mode_col=st.columns([1,2])
    with kv_col:
        kv_scanner=st.radio("kV du scanner",[80,90,100,110,120],index=4,horizontal=True)
    with mode_col:
        modes=["Portal","Artériel"]
        if config.get("intermediate_enabled",False): modes.append("Intermédiaire")
        injection_mode=st.radio("Mode d’injection",modes,horizontal=True)
        if injection_mode=="Portal": base_time=config.get("portal_time",30.0)
        elif injection_mode=="Artériel": base_time=config.get("arterial_time",25.0)
        else: base_time=st.number_input("Temps intermédiaire (s)",value=float(config.get("intermediate_time",28.0)),min_value=5,max_value=120,step=1.0)
        st.markdown(f"**Départ d’acquisition (s)** : {calculate_acq_start(age,config):.1f}")
        st.markdown(f"**Concentration (mg I/mL)** : {int(config.get('concentration_mg_ml',350))}")

    volume,bsa=calculate_volume(weight,height,kv_scanner,float(config.get("concentration_mg_ml",350)),imc,config.get("calc_mode","Charge iodée"),config.get("charges",{}))
    injection_rate, injection_time, time_adjusted=adjust_rate(volume,float(base_time),float(config.get("max_debit",6.0)))

    res_col1,res_col2=st.columns(2,gap="medium")
    for col,title,val,note in zip([res_col1,res_col2],["💧 Volume appliqué","🚀 Débit recommandé"],[volume,injection_rate],["Limité à 200 mL",""]):
        col.markdown(f"""<div class="result-card">
        <h3 style="color:{GUERBET_BLUE}; margin-bottom:6px;">{title}</h3>
        <h1 style="color:{GUERBET_DARK}; margin:0;">{val:.1f} {'mL' if 'Volume' in title else 'mL/s'}</h1>
        <div class='small-note'>{note}</div></div>""",unsafe_allow_html=True)
    if time_adjusted: st.warning(f"⚠️ Temps ajusté à {injection_time:.1f}s pour respecter le débit max de {config.get('max_debit',6.0)} mL/s.")
    st.info(f"📏 IMC : {imc:.1f}" + (f" | Surface corporelle : {bsa:.2f} m²" if bsa else ""))
    st.markdown("""<div style='background-color:#FCE8E6;color:#6B1A00;padding:10px;border-radius:8px;margin-top:15px;font-size:0.9rem;'>⚠️ <b>Avertissement :</b> Outil indicatif, valider par un professionnel de santé.</div>""",unsafe_allow_html=True)

# ===================== Footer =====================
st.markdown(f"""<div style='text-align:center;margin-top:20px;font-size:0.8rem;color:#666;'>
© 2025 Guerbet | Développé par <b>Sébastien Partouche</b><br>
Ce logiciel fournit des <b>propositions de valeurs</b> et ne remplace pas le jugement médical.<br>
<div style='display:inline-block;background-color:#FCE8B2;border:1px solid #F5B800;padding:8px 15px;border-radius:10px;color:#5A4500;font-weight:600;margin-top:10px;'>🧪 Version BETA TEST – Usage interne / évaluation</div>
</div>""",unsafe_allow_html=True)
