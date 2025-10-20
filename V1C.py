# -*- coding: utf-8 -*-
"""
Calculette complète (une page) de dose de produit de contraste — CT Oncologie adulte
Adaptée pour Sébastien Partouche — version consolidée optimisée (corrigée & synchronisée)
Usage : streamlit run calculatrice_contraste_oncologie_corrigee_v3.py
"""

import streamlit as st
import json, os, math, base64, time, contextlib
from datetime import datetime
import pandas as pd

# ------------------------
# Fichiers de config
# ------------------------
CONFIG_FILE = "iodine_config.json"
USER_SESSIONS_FILE = "user_sessions.json"
LOG_FILE = "calc_audit.log"

# ------------------------
# Valeurs par défaut
# ------------------------
default_config = {
    "charges": {str(kv): val for kv, val in zip([80, 90, 100, 110, 120], [0.35, 0.38, 0.40, 0.42, 0.45])},
    "concentration_mg_ml": 350,
    "portal_time": 30.0,
    "arterial_time": 25.0,
    "intermediate_enabled": False,
    "intermediate_time": 28.0,
    "acquisition_start_param": 70.0,
    "auto_acquisition_by_age": True,
    "max_debit": 6.0,
    "rincage_volume": 35.0,
    "rincage_delta_debit": 0.5,
    "calc_mode": "Charge iodée",
    "simultaneous_enabled": False,
    "target_concentration": 350,
    "volume_max_limit": 200.0,
    "super_user": "admin"
}

# ------------------------
# Utils I/O
# ------------------------
@contextlib.contextmanager
def file_lock(lock_path, timeout=5.0, poll=0.05):
    start = time.time()
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd); break
        except FileExistsError:
            if time.time() - start > timeout:
                raise TimeoutError(f"Lock timeout: {lock_path}")
            time.sleep(poll)
    try:
        yield
    finally:
        try: os.remove(lock_path)
        except FileNotFoundError: pass

def audit_log(msg):
    try:
        ts = datetime.utcnow().isoformat()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{ts} - {msg}\n")
    except Exception:
        pass

def load_json_safe(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            audit_log(f"LOAD_ERROR {path}: {e}")
    return default.copy()

def save_json_atomic(path, data):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        audit_log(f"SAVE_ERROR {path}: {e}")

def img_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

# ------------------------
# Charger config & sessions
# ------------------------
config_global = load_json_safe(CONFIG_FILE, default_config)
user_sessions = load_json_safe(USER_SESSIONS_FILE, {})

# Normalisation sessions
for uid, data in list(user_sessions.items()):
    if not isinstance(data, dict):
        user_sessions[uid] = {"programs": {}, "config": config_global.copy(), "email": None, "created": datetime.utcnow().isoformat()}
    else:
        data.setdefault("programs", {})
        data.setdefault("config", config_global.copy())
        data.setdefault("email", None)
        data.setdefault("created", datetime.utcnow().isoformat())

# ------------------------
# Calculs
# ------------------------
def calculate_bsa(weight, height):
    try: return math.sqrt((height * weight) / 3600.0)
    except Exception: return None

def calculate_volume(weight, height, kv, concentration_mg_ml, imc, calc_mode, charges, volume_cap):
    kv_factors = {80: 11, 90: 13, 100: 15, 110: 16.5, 120: 18.6}
    concentration_g_ml = concentration_mg_ml / 1000.0
    bsa = None
    try:
        if calc_mode == "Surface corporelle" or (calc_mode.startswith("Charge iodée sauf") and imc >= 30):
            bsa = calculate_bsa(weight, height)
            factor = kv_factors.get(kv, 15)
            volume = (bsa * factor) / concentration_g_ml
        else:
            charge_iodine = float(charges.get(str(kv), 0.4))
            volume = (weight * charge_iodine) / concentration_g_ml
    except Exception as e:
        audit_log(f"CALC_VOLUME_ERROR: {e}")
        volume = 0.0
    volume = max(0.0, float(volume))
    if volume > volume_cap:
        volume = volume_cap
    return volume, bsa

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
    injection_time = max(1.0, float(injection_time))
    injection_rate = volume / injection_time
    time_adjusted = False
    if injection_rate > max_debit:
        injection_time = volume / max_debit
        injection_rate = max_debit
        time_adjusted = True
    return float(injection_rate), float(injection_time), bool(time_adjusted)

# ------------------------
# Streamlit UI init
# ------------------------
st.set_page_config(page_title="Calculette contraste CT – Oncologie adulte", page_icon="💉", layout="wide")
st.markdown("""
<style>
.stApp { background-color:#F7FAFC; font-family:'Segoe UI', sans-serif; }
.slider-red .stSlider [data-baseweb="slider"] div[role="slider"] { background-color:#E53935 !important; }
.slider-red .stSlider [data-baseweb="slider"] div[role="slider"]::before { background-color:#E53935 !important; }
.section-title { font-size:22px; font-weight:700; color:#123A5F; margin-bottom: 12px; text-align:center; }
.divider { border-left:1px solid #d9d9d9; height:100%; margin:0 10px; }
.info-block { background:#F5F8FC; border-radius:10px; padding:12px 16px; text-align:center; color:#123A5F; box-shadow:0 1px 3px rgba(0,0,0,0.05); }
</style>
""", unsafe_allow_html=True)

# session state
if "accepted_legal" not in st.session_state: st.session_state["accepted_legal"] = False
if "user_id" not in st.session_state: st.session_state["user_id"] = None
if "user_config" not in st.session_state: st.session_state["user_config"] = config_global.copy()
if "selected_program_global" not in st.session_state: st.session_state["selected_program_global"] = "Aucun"
if "program_unlocked" not in st.session_state: st.session_state["program_unlocked"] = False

SUPER_USER = config_global.get("super_user", "admin")

def get_cfg():
    return st.session_state.get("user_config", config_global.copy())

def set_cfg_and_persist(user_id, new_cfg):
    st.session_state["user_config"] = new_cfg.copy()
    user_sessions.setdefault(user_id, {"programs": {}, "config": new_cfg.copy(), "email": None, "created": datetime.utcnow().isoformat()})
    user_sessions[user_id]["config"] = new_cfg.copy()
    save_json_atomic(USER_SESSIONS_FILE, user_sessions)

# ------------------------
# Page d'accueil : légal + login
# ------------------------
if not st.session_state["accepted_legal"] or st.session_state["user_id"] is None:
    st.markdown("### ⚠️ Mentions légales — acceptation requise")
    st.markdown("Avant utilisation, acceptez la mention légale et entrez votre identifiant. Résultats **indicatifs** à valider par un professionnel de santé.")
    accept = st.checkbox("✅ J’accepte les mentions légales.", key="accept_checkbox")

    st.markdown("**Se connecter**")
    existing_id_input = st.text_input("Entrez un identifiant existant", key="existing_id_input")
    st.markdown("— ou —")
    st.markdown("**Créer un nouvel identifiant**")
    new_user_id = st.text_input("Créez un nouvel identifiant", key="new_id_input")
    new_user_email = st.text_input("(Facultatif) Email pour récupération d'identifiant", key="new_user_email")

    with st.expander("🔑 Identifiant oublié ?"):
        forget_email = st.text_input("Email associé", key="forget_email")
        if st.button("🔍 Rechercher identifiant par email"):
            email = forget_email.strip()
            if not email:
                st.warning("Veuillez saisir un email.")
            else:
                found = [uid for uid, info in user_sessions.items() if info.get("email") == email]
                st.success(f"Identifiant(s) : {', '.join(found)}") if found else st.error("Aucun identifiant trouvé.")

    if st.button("Entrer dans la session"):
        if not accept:
            st.warning("Vous devez accepter les mentions légales.")
        else:
            chosen_existing = existing_id_input.strip()
            chosen_new = new_user_id.strip()
            email_new = new_user_email.strip() if new_user_email else None
            if chosen_existing and chosen_new:
                st.warning("Choisissez soit un identifiant existant, soit créez-en un nouveau (pas les deux).")
            elif chosen_existing:
                if chosen_existing not in user_sessions:
                    st.error("❌ Identifiant introuvable.")
                else:
                    st.session_state["accepted_legal"] = True
                    st.session_state["user_id"] = chosen_existing
                    st.session_state["user_config"] = user_sessions[chosen_existing].get("config", config_global.copy()).copy()
            elif chosen_new:
                if chosen_new in user_sessions:
                    st.error("❌ Cet identifiant existe déjà.")
                else:
                    if email_new:
                        emails = [info.get("email") for info in user_sessions.values() if info.get("email")]
                        if email_new in emails:
                            st.error("❌ Email déjà utilisé.")
                            st.stop()
                    ts = datetime.utcnow().isoformat()
                    user_sessions[chosen_new] = {"programs": {}, "config": config_global.copy(), "email": email_new, "created": ts, "last_selected_program": None}
                    save_json_atomic(USER_SESSIONS_FILE, user_sessions)
                    st.session_state["accepted_legal"] = True
                    st.session_state["user_id"] = chosen_new
                    st.session_state["user_config"] = config_global.copy()
                    st.success(f"Identifiant '{chosen_new}' créé.")
            else:
                st.warning("Veuillez saisir un identifiant existant ou en créer un.")
    st.stop()

# ------------------------
# Header
# ------------------------
st.markdown(
    """
    <div style="display:flex; align-items:center; gap:8px; background:#124F7A; padding:8px; border-radius:8px">
        <h2 style="color:white; margin:0; font-size:26px;">
            Calculette de dose de produit de contraste en CT — Oncologie adulte
        </h2>
    </div>
    """, unsafe_allow_html=True
)

# ------------------------
# Tabs
# ------------------------
tab_patient, tab_params, tab_tutorial = st.tabs(["🧍 Patient", "⚙️ Paramètres", "📘 Tutoriel"])

# ------------------------
# Onglet Paramètres
# ------------------------
with tab_params:
    st.header("⚙️ Paramètres et Bibliothèque (personnelle)")
    user_id = st.session_state["user_id"]
    cfg = get_cfg()

    # Programmes
    st.subheader("📚 Vos programmes personnels")
    personal_programs = user_sessions.get(user_id, {}).get("programs", {})
    program_list = ["Aucun"] + list(personal_programs.keys())
    current_index = program_list.index(st.session_state["selected_program_global"]) if st.session_state["selected_program_global"] in program_list else 0

    program_choice = st.selectbox("Programme (Personnel)", program_list, index=current_index, key="prog_params_personal")
    # synchro vers Patient
    st.session_state["selected_program_global"] = program_choice

    # Charger config si programme choisi
    if program_choice != "Aucun":
        prog_conf = personal_programs.get(program_choice, {})
        for key, val in prog_conf.items():
            cfg[key] = val

    program_selected = (st.session_state["selected_program_global"] != "Aucun")
    disabled = (program_selected and not st.session_state["program_unlocked"])

    if program_choice != "Aucun":
        st.info(f"🔒 Programme sélectionné : **{program_choice}** — protégé.")
        pwd_input = st.text_input("Entrez votre identifiant pour déverrouiller", type="password")
        if st.button("🔓 Déverrouiller"):
            if pwd_input.strip() == user_id:
                st.session_state["program_unlocked"] = True
                st.success(f"✅ '{program_choice}' déverrouillé.")
            else:
                st.session_state["program_unlocked"] = False
                st.error("❌ Identifiant incorrect.")
    else:
        st.info("Aucun programme sélectionné — modification libre et enregistrement possible.")

    new_prog_name = st.text_input("Nom du nouveau programme (enregistrer/mettre à jour)")

    # Paramètres d’injection
    st.markdown("---")
    st.subheader("💉 Paramètres d’injection et calculs")
    cfg["simultaneous_enabled"] = st.checkbox("Activer l'injection simultanée", value=cfg.get("simultaneous_enabled", False), disabled=disabled)
    if cfg["simultaneous_enabled"]:
        cfg["target_concentration"] = st.number_input("Concentration cible (mg I/mL)", value=int(cfg.get("target_concentration", 350)), min_value=200, max_value=500, step=10, disabled=disabled)

    cfg["concentration_mg_ml"] = st.selectbox("Concentration (mg I/mL)", [300,320,350,370,400], index=[300,320,350,370,400].index(int(cfg.get("concentration_mg_ml", 350))), disabled=disabled)
    cfg["calc_mode"] = st.selectbox("Méthode de calcul", ["Charge iodée", "Surface corporelle", "Charge iodée sauf IMC > 30 → Surface corporelle"], index=["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"].index(cfg.get("calc_mode","Charge iodée")), disabled=disabled)
    cfg["max_debit"] = st.number_input("Débit maximal autorisé (mL/s)", value=float(cfg.get("max_debit",6.0)), min_value=1.0, max_value=20.0, step=0.1, disabled=disabled)

    # Acquisition & temps
    st.markdown("---")
    st.subheader("⏱ Départ d’acquisition et temps d’injection")
    cfg["auto_acquisition_by_age"] = st.checkbox("Ajuster automatiquement le départ d’acquisition selon l’âge", value=bool(cfg.get("auto_acquisition_by_age", True)), disabled=disabled)
    if not cfg["auto_acquisition_by_age"]:
        cfg["acquisition_start_param"] = st.number_input("Départ d’acquisition manuel (s)", value=float(cfg.get("acquisition_start_param", 70.0)), min_value=30.0, max_value=120.0, step=1.0, disabled=disabled)

    cfg["portal_time"] = st.number_input("Portal (s)", value=float(cfg.get("portal_time", 30.0)), min_value=5.0, max_value=120.0, step=1.0, disabled=disabled)
    cfg["arterial_time"] = st.number_input("Artériel (s)", value=float(cfg.get("arterial_time", 25.0)), min_value=5.0, max_value=120.0, step=1.0, disabled=disabled)
    cfg["intermediate_enabled"] = st.checkbox("Activer temps intermédiaire", value=bool(cfg.get("intermediate_enabled", False)), disabled=disabled)
    if cfg["intermediate_enabled"]:
        cfg["intermediate_time"] = st.number_input("Intermédiaire (s)", value=float(cfg.get("intermediate_time", 28.0)), min_value=5.0, max_value=120.0, step=1.0, disabled=disabled)

    # Rinçage & volumes
    cfg["rincage_volume"] = st.number_input("Volume rinçage (mL)", value=float(cfg.get("rincage_volume", 35.0)), min_value=10.0, max_value=100.0, step=1.0, disabled=disabled)
    cfg["rincage_delta_debit"] = st.number_input("Δ débit NaCl vs contraste (mL/s)", value=float(cfg.get("rincage_delta_debit", 0.5)), min_value=0.1, max_value=5.0, step=0.1, disabled=disabled)
    cfg["volume_max_limit"] = st.number_input("Plafond volume (mL) - seringue", value=float(cfg.get("volume_max_limit", 200.0)), min_value=50.0, max_value=500.0, step=10.0, disabled=disabled)

    # Charges iodées
    st.markdown("---")
    st.subheader("💊 Charges en iode par kV (g I/kg)")
    df_charges = pd.DataFrame({"kV":[80,90,100,110,120], "Charge (g I/kg)":[float(cfg["charges"].get(str(kv), 0.35)) for kv in [80,90,100,110,120]]})
    edited_df = st.data_editor(df_charges, num_rows="fixed", use_container_width=True, disabled=disabled)

    if st.button("💾 Sauvegarder les paramètres", disabled=disabled):
        cfg["charges"] = {str(int(row.kV)): float(row["Charge (g I/kg)"]) for _, row in edited_df.iterrows()}
        set_cfg_and_persist(user_id, cfg)
        st.success("✅ Paramètres sauvegardés !")

    # Enregistrer programme
    if st.button("💾 Ajouter/Mise à jour programme"):
        if program_selected and not st.session_state["program_unlocked"]:
            st.warning("Programme protégé — déverrouillez ou sauvegardez sous un **nouveau nom**.")
        elif not new_prog_name.strip():
            st.warning("Donnez un nom au programme.")
        else:
            user_sessions.setdefault(user_id, {}).setdefault("programs", {})[new_prog_name.strip()] = cfg.copy()
            user_sessions[user_id]["config"] = cfg.copy()
            save_json_atomic(USER_SESSIONS_FILE, user_sessions)
            st.session_state["selected_program_global"] = new_prog_name.strip()
            st.success(f"✅ Programme '{new_prog_name}' sauvegardé.")

    # Suppression programme
    st.markdown("**Gérer mes programmes personnels**")
    personal_prog_list = list(user_sessions.get(user_id, {}).get("programs", {}).keys())
    if personal_prog_list:
        del_prog_personal = st.selectbox("Supprimer un programme personnel", [""] + personal_prog_list, key="del_prog_personal")
        if st.button("🗑 Supprimer programme (Personnel)"):
            if del_prog_personal and del_prog_personal in user_sessions[user_id]["programs"]:
                del user_sessions[user_id]["programs"][del_prog_personal]
                save_json_atomic(USER_SESSIONS_FILE, user_sessions)
                st.success(f"Programme '{del_prog_personal}' supprimé.")
            else:
                st.error("Programme introuvable.")
    else:
        st.info("Aucun programme enregistré pour l’instant.")

    # Gestion des identifiants
    st.markdown("---")
    st.subheader("🗂 Gestion des sessions / identifiants")
    all_user_ids = sorted(list(user_sessions.keys()))
    if user_id == SUPER_USER:
        st.markdown("**Super-utilisateur : accès à tous les identifiants**")
        df_users = pd.DataFrame([{"identifiant": uid, "email": user_sessions[uid].get("email")} for uid in all_user_ids])
        st.dataframe(df_users, use_container_width=True)
        del_input = st.text_input("Identifiant à supprimer (exact)", key="del_input_admin")
        if st.button("🗑 Supprimer identifiant (super-utilisateur)"):
            target = del_input.strip()
            if not target: st.warning("Saisir un identifiant.")
            elif target == user_id: st.error("Impossible de supprimer l’identifiant en cours.")
            elif target not in user_sessions: st.error("Identifiant introuvable.")
            else:
                del user_sessions[target]; save_json_atomic(USER_SESSIONS_FILE, user_sessions)
                st.success(f"Identifiant '{target}' supprimé.")
    else:
        st.markdown("Seul le super-utilisateur peut lister tous les identifiants.")
        del_input_self = st.text_input("Confirmez votre identifiant pour supprimer votre compte (exact)", key="del_input_self")
        if st.button("🗑 Supprimer MON identifiant"):
            target = del_input_self.strip()
            if not target: st.warning("Saisir votre identifiant exact.")
            elif target != user_id: st.error("Nom saisi ≠ identifiant connecté.")
            else:
                if user_id in user_sessions:
                    del user_sessions[user_id]; save_json_atomic(USER_SESSIONS_FILE, user_sessions)
                st.session_state["accepted_legal"] = False
                st.session_state["user_id"] = None
                st.session_state["user_config"] = config_global.copy()
                st.success("Identifiant supprimé. Déconnexion effectuée.")
                st.rerun()

# ------------------------
# Onglet Patient
# ------------------------
with tab_patient:
    # Styles spécifiques (remonter les blocs, radios centrées)
    st.markdown("""
        <style>
        /* Réduction espace vertical entre sliders et blocs */
        div[data-testid="stHorizontalBlock"] { margin-top:-22px !important; }
        div.block-container { padding-top: 0rem !important; }

        /* Titres */
        .section-title { font-size:22px; font-weight:700; color:#123A5F; margin-bottom:12px; text-align:center; }
        .block-title { text-align:center; font-weight:700; color:#123A5F; font-size:16px; margin-bottom:6px; }

        /* Radios centrées sur une ligne, sans wrap */
        div[role="radiogroup"] { display:flex !important; justify-content:center !important; align-items:center !important; flex-wrap:nowrap !important; gap:6px !important; }
        div[role="radiogroup"] label { font-size:13px !important; padding:0 4px !important; margin:0 1px !important; white-space:nowrap !important; }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<div class='section-title'>🧍 Informations patient</div>", unsafe_allow_html=True)

    # Sliders
    st.markdown("<div class='slider-red'>", unsafe_allow_html=True)
    current_year = datetime.now().year
    col_poids, col_taille, col_annee, col_prog = st.columns([1, 1, 1, 1.3])

    with col_poids:
        weight = st.slider("Poids (kg)", 20, 200, 70)
    with col_taille:
        height = st.slider("Taille (cm)", 100, 220, 170)
    with col_annee:
        birth_year = st.slider("Année de naissance", current_year - 120, current_year, 1985)
    with col_prog:
        user_id = st.session_state["user_id"]
        user_programs = user_sessions.get(user_id, {}).get("programs", {})
        program_list = ["Aucun"] + list(user_programs.keys())
        current_index = program_list.index(st.session_state["selected_program_global"]) if st.session_state["selected_program_global"] in program_list else 0
        prog_choice_patient = st.selectbox("Sélection d'un programme", program_list, index=current_index, key="prog_choice_patient")
        # synchro vers Paramètres + relock
        st.session_state["selected_program_global"] = prog_choice_patient
        st.session_state["program_unlocked"] = False
        if prog_choice_patient != "Aucun":
            prog_conf = user_programs.get(prog_choice_patient, {})
            cfg_tmp = get_cfg()
            for k,v in prog_conf.items(): cfg_tmp[k] = v
            set_cfg_and_persist(user_id, cfg_tmp)
            user_sessions[user_id]["last_selected_program"] = prog_choice_patient
            save_json_atomic(USER_SESSIONS_FILE, user_sessions)
    st.markdown("</div>", unsafe_allow_html=True)

    # Variables patient
    cfg = get_cfg()
    age = current_year - birth_year
    imc = weight / ((height/100)**2)

    # Blocs 3 colonnes
    col_left, col_div1, col_center, col_div2, col_right = st.columns([1.2, 0.05, 1.2, 0.05, 1.2])

    with col_left:
        st.markdown("<div class='block-title'>Paramètres principaux</div>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([0.2, 1, 0.2])
        with c2:
            kv_scanner = st.radio("kV", [80, 90, 100, 110, 120], horizontal=True, index=4, label_visibility="collapsed", key="kv_scanner_patient")
        charge_iod = float(cfg.get("charges", {}).get(str(kv_scanner), 0.45))
        concentration = int(cfg.get("concentration_mg_ml", 350))
        calc_mode_label = cfg.get("calc_mode", "Charge iodée")
        st.markdown(f"<div style='text-align:center; font-size:15px; color:#123A5F;'><b>Charge iodée :</b> {charge_iod:.2f} g I/kg<br><b>Concentration :</b> {concentration} mg I/mL<br><b>Méthode :</b> {calc_mode_label}</div>", unsafe_allow_html=True)

    with col_div1: st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    with col_center:
        st.markdown("<div class='block-title'>Injection et timing</div>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([0.2, 1, 0.2])
        with c2:
            injection_modes = ["Portal", "Artériel"]
            if cfg.get("intermediate_enabled", False):
                injection_modes.append("Intermédiaire")
            injection_mode = st.radio("Mode d'injection", injection_modes, horizontal=True, index=0, key="injection_mode_patient", label_visibility="collapsed")
        if injection_mode == "Portal": base_time = float(cfg.get("portal_time", 30.0))
        elif injection_mode == "Artériel": base_time = float(cfg.get("arterial_time", 25.0))
        elif injection_mode == "Intermédiaire": base_time = float(cfg.get("intermediate_time", 28.0))
        else: base_time = float(cfg.get("portal_time", 30.0))

        acquisition_start = calculate_acquisition_start(age, cfg)
        st.markdown(f"<div style='text-align:center; font-size:15px; color:#123A5F;'><b>Temps {injection_mode.lower()} :</b> {base_time:.0f} s<br><b>Départ d'acquisition :</b> {acquisition_start:.1f} s</div>", unsafe_allow_html=True)

        if injection_mode == "Intermédiaire":
            st.markdown("""
                <div style='background-color:#E3F2FD; border-left:4px solid #1976D2;
                            padding:8px 10px; margin-top:6px; border-radius:6px;
                            color:#0D47A1; font-size:13px; text-align:center;'>
                    ⚠️ <b>Attention :</b> pensez à ajuster le départ d’acquisition.
                </div>""", unsafe_allow_html=True)
            new_intermediate_time = st.number_input("Modifier temps intermédiaire (s)", value=float(cfg.get("intermediate_time", 28.0)), min_value=5.0, max_value=120.0, step=1.0, key="patient_intermediate_time")
            cfg["intermediate_time"] = float(new_intermediate_time)
            set_cfg_and_persist(st.session_state["user_id"], cfg)

    with col_div2: st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    with col_right:
        st.markdown("<div class='block-title'>Options avancées</div>", unsafe_allow_html=True)
        auto_age = bool(cfg.get("auto_acquisition_by_age", True))
        sim_enabled = bool(cfg.get("simultaneous_enabled", False))
        st.markdown(f"<div style='text-align:center; font-size:15px; color:#123A5F;'><b>Ajustement automatique selon l'âge :</b><br>{'✅ activé' if auto_age else '❌ désactivé'}<br><br><b>Injection simultanée :</b><br>{'✅ activée' if sim_enabled else '❌ désactivée'}</div>", unsafe_allow_html=True)

    # Calculs finaux
    volume, bsa = calculate_volume(weight, height, kv_scanner, float(cfg.get("concentration_mg_ml", 350)), imc, cfg.get("calc_mode", "Charge iodée"), cfg.get("charges", {}), float(cfg.get("volume_max_limit", 200.0)))
    injection_rate, injection_time, time_adjusted = adjust_injection_rate(volume, float(base_time), float(cfg.get("max_debit", 6.0)))

    st.markdown("---")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"<h4 style='text-align:center;'>💧 Volume contraste</h4><h2 style='text-align:center;'>{int(volume)} mL</h2>", unsafe_allow_html=True)
    with col2:
        st.markdown(f"<h4 style='text-align:center;'>💧 Volume NaCl</h4><h2 style='text-align:center;'>{int(cfg.get('rincage_volume', 35.0))} mL</h2>", unsafe_allow_html=True)
    with col3:
        st.markdown(f"<h4 style='text-align:center;'>🚀 Débit</h4><h2 style='text-align:center;'>{injection_rate:.1f} mL/s</h2>", unsafe_allow_html=True)

    if time_adjusted:
        st.warning(f"⚠️ Temps ajusté à {injection_time:.1f}s (max {float(cfg.get('max_debit',6.0)):.1f} mL/s).")

    st.info(f"📏 IMC : {imc:.1f}" + (f" | Surface corporelle : {bsa:.2f} m²" if bsa else ""))

# ------------------------
# Onglet Tutoriel
# ------------------------
with tab_tutorial:
    st.title("📘 Tutoriel — Mode d'emploi et principes cliniques")
    st.markdown("""
    1. **Patient** : saisissez poids, taille et année de naissance.  
    2. **Programme** : sélectionnez un programme (ou créez-en un dans Paramètres).  
    3. **Injection** : choisissez le mode (Portal/Artériel/Intermédiaire).  
    4. **Résultats** : volume de contraste, NaCl, et débit conseillé.
    """)
    st.header("🧠 Explications")
    st.markdown("""
    - **Charge iodée** proportionnelle au poids.  
    - **Surface corporelle (BSA)** si IMC>30 (option mixte).  
    - **Débit** ajusté si dépasse le maximum.  
    - **Injection simultanée** : dilution pour atteindre la concentration cible.
    """)

# ------------------------
# Footer
# ------------------------
st.markdown("""<div style='text-align:center; margin-top:20px; font-size:0.8rem; color:#666;'>
© 2025 Guerbet | Développé par <b>Sébastien Partouche</b><br>
Calculette de dose de produit de contraste en CT — Oncologie adulte.<br>
<div style='display:inline-block; background-color:#FCE8B2; border:1px solid #F5B800; padding:8px 15px; border-radius:10px; color:#5A4500; font-weight:600; margin-top:10px;'>🧪 Version BETA TEST – Usage interne / évaluation</div>
</div>""", unsafe_allow_html=True)
