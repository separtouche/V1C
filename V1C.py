# -*- coding: utf-8 -*-
"""
Calculette de dose de produit de contraste — CT Oncologie adulte
Version complète synchronisée (Patient <-> Paramètres) + verrouillage + visuel conservé
Usage : streamlit run calculatrice_contraste_ct_sync_final.py
"""

import streamlit as st
import json, os, math, base64
from datetime import datetime
import pandas as pd

# ------------------------
# Fichiers de config
# ------------------------
CONFIG_FILE = "iodine_config.json"
USER_SESSIONS_FILE = "user_sessions.json"

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
# Utils simples
# ------------------------
def load_json_safe(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return default.copy()
    return default.copy()

def save_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    os.replace(tmp, path)

def img_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

# ------------------------
# Métier
# ------------------------
def calculate_bsa(weight, height):
    try:
        return math.sqrt((height * weight) / 3600.0)
    except Exception:
        return None

def calculate_volume(weight, height, kv, concentration_mg_ml, imc, calc_mode, charges, volume_cap):
    kv_factors = {80: 11, 90: 13, 100: 15, 110: 16.5, 120: 18.6}
    concentration_g_ml = concentration_mg_ml / 1000.0
    bsa = None
    try:
        if calc_mode == "Surface corporelle" or (calc_mode.startswith("Charge iodée sauf") and imc >= 30):
            bsa = calculate_bsa(weight, height)
            factor = kv_factors.get(kv, 15)
            volume = bsa * factor / concentration_g_ml
        else:
            charge_iodine = float(charges.get(str(kv), 0.4))
            volume = weight * charge_iodine / concentration_g_ml
    except Exception:
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
    injection_time = float(injection_time) if injection_time > 0 else 1.0
    injection_rate = volume / injection_time
    if injection_rate > max_debit:
        injection_time = volume / max_debit
        injection_rate = max_debit
        return float(injection_rate), float(injection_time), True
    return float(injection_rate), float(injection_time), False

# ------------------------
# Données persistantes
# ------------------------
config_global = load_json_safe(CONFIG_FILE, default_config)
user_sessions = load_json_safe(USER_SESSIONS_FILE, {})

# Normalisation des sessions
for uid, data in list(user_sessions.items()):
    if not isinstance(data, dict):
        user_sessions[uid] = {
            "programs": {},
            "config": config_global.copy(),
            "email": None,
            "created": datetime.utcnow().isoformat(),
            "last_selected_program": "Aucun"
        }
    else:
        data.setdefault("programs", {})
        data.setdefault("config", config_global.copy())
        data.setdefault("email", None)
        data.setdefault("created", datetime.utcnow().isoformat())
        data.setdefault("last_selected_program", "Aucun")

# ------------------------
# Streamlit setup & state
# ------------------------
st.set_page_config(page_title="Calculette Contraste CT — Oncologie adulte", page_icon="💉", layout="wide")

if "accepted_legal" not in st.session_state:
    st.session_state["accepted_legal"] = False
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
if "user_config" not in st.session_state:
    st.session_state["user_config"] = config_global.copy()
if "selected_program_global" not in st.session_state:
    st.session_state["selected_program_global"] = "Aucun"
if "program_unlocked" not in st.session_state:
    st.session_state["program_unlocked"] = False

SUPER_USER = config_global.get("super_user", "admin")

def get_cfg():
    return st.session_state.get("user_config", config_global.copy())

def set_cfg_and_persist(uid, new_cfg):
    st.session_state["user_config"] = new_cfg.copy()
    user_sessions.setdefault(uid, {}).setdefault("config", new_cfg.copy())
    user_sessions[uid]["config"] = new_cfg.copy()
    save_json_atomic(USER_SESSIONS_FILE, user_sessions)

def set_selected_program(choice: str):
    # Synchronisation centrale + verrouillage auto
    st.session_state["selected_program_global"] = choice
    st.session_state["program_unlocked"] = False
    uid = st.session_state.get("user_id")
    if uid:
        user_sessions.setdefault(uid, {}).setdefault("last_selected_program", "Aucun")
        user_sessions[uid]["last_selected_program"] = choice
        save_json_atomic(USER_SESSIONS_FILE, user_sessions)

# ------------------------
# Page d’accueil (mentions + login)
# ------------------------
if not st.session_state["accepted_legal"] or st.session_state["user_id"] is None:
    st.markdown("### ⚠️ Mentions légales — acceptation requise")
    st.markdown("Avant utilisation, acceptez la mention légale et entrez votre identifiant. Résultats indicatifs à valider par un professionnel de santé.")
    accept = st.checkbox("✅ J’accepte les mentions légales.", key="accept_checkbox")
    existing_id_input = st.text_input("Identifiant existant", key="existing_id_input")
    new_user_id = st.text_input("Créer un identifiant (si nouveau)", key="new_id_input")
    if st.button("Entrer dans la session"):
        if not accept:
            st.warning("Vous devez accepter les mentions légales.")
        else:
            chosen_existing = existing_id_input.strip()
            chosen_new = new_user_id.strip()
            if chosen_existing and chosen_new:
                st.warning("Saisissez soit un identifiant existant, soit créez-en un nouveau (pas les deux).")
            elif chosen_existing:
                if chosen_existing not in user_sessions:
                    st.error("❌ Identifiant introuvable.")
                else:
                    st.session_state["accepted_legal"] = True
                    st.session_state["user_id"] = chosen_existing
                    st.session_state["user_config"] = user_sessions[chosen_existing].get("config", config_global.copy()).copy()
                    set_selected_program(user_sessions[chosen_existing].get("last_selected_program", "Aucun"))
            elif chosen_new:
                if chosen_new in user_sessions:
                    st.error("❌ Cet identifiant existe déjà.")
                else:
                    user_sessions[chosen_new] = {
                        "programs": {},
                        "config": config_global.copy(),
                        "email": None,
                        "created": datetime.utcnow().isoformat(),
                        "last_selected_program": "Aucun"
                    }
                    save_json_atomic(USER_SESSIONS_FILE, user_sessions)
                    st.session_state["accepted_legal"] = True
                    st.session_state["user_id"] = chosen_new
                    st.session_state["user_config"] = config_global.copy()
                    set_selected_program("Aucun")
                    st.success(f"Identifiant '{chosen_new}' créé.")
            else:
                st.warning("Entrez un identifiant existant ou créez-en un.")
    st.stop()

# ------------------------
# Header (visuel conservé)
# ------------------------
logo_path = "guerbet_logo.png"
if os.path.exists(logo_path):
    try:
        img_b64 = img_to_base64(logo_path)
        st.markdown(f"""
        <div style="display:flex; align-items:center; gap:8px; background:#124F7A; padding:8px; border-radius:8px">
            <img src="data:image/png;base64,{img_b64}" style="height:55px"/>
            <h2 style="color:white; margin:0; font-size:26px;">
                Calculette de dose de produit de contraste en CT — Oncologie adulte
            </h2>
        </div>
        """, unsafe_allow_html=True)
    except Exception:
        st.title("Calculette de dose de produit de contraste en CT — Oncologie adulte")
else:
    st.title("Calculette de dose de produit de contraste en CT — Oncologie adulte")

# ------------------------
# CSS (conservé)
# ------------------------
st.markdown("""
<style>
.stApp { background-color: #F7FAFC; font-family: 'Segoe UI', sans-serif; }
.slider-red .stSlider [data-baseweb="slider"] div[role="slider"] { background-color: #E53935 !important; }
.slider-red .stSlider [data-baseweb="slider"] div[role="slider"]::before { background-color: #E53935 !important; }
.divider { border-left: 1px solid #d9d9d9; height: 100%; margin: 0 20px; }
.info-block { background: #F5F8FC; border-radius: 10px; padding: 15px 20px; text-align: center; color: #123A5F; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
.section-title { font-size: 22px; font-weight: 700; color: #123A5F; margin-bottom: 15px; }
</style>
""", unsafe_allow_html=True)

# ------------------------
# Onglets
# ------------------------
tab_patient, tab_params, tab_tutorial = st.tabs(["🧍 Patient", "⚙️ Paramètres", "📘 Tutoriel"])

# =========================================================
# ⚙️ Onglet Paramètres — complet + synchro + verrouillage
# =========================================================
with tab_params:
    st.header("⚙️ Paramètres et Bibliothèque (personnelle)")
    user_id = st.session_state["user_id"]
    cfg = get_cfg()

    # --- Vos programmes personnels (synchronisé) ---
    st.subheader("📚 Vos programmes personnels")
    personal_programs = user_sessions.get(user_id, {}).get("programs", {})
    prog_list = ["Aucun"] + list(personal_programs.keys())

    # index basé sur l'état global
    current_prog = st.session_state["selected_program_global"]
    idx_params = prog_list.index(current_prog) if current_prog in prog_list else 0

    program_choice = st.selectbox(
        "Programme (Personnel)",
        prog_list,
        index=idx_params,
        key="prog_params_select"
    )

    # synchro centrale si changement
    if program_choice != st.session_state["selected_program_global"]:
        set_selected_program(program_choice)

    # appliquer la config du programme si choisi
    if program_choice != "Aucun":
        prog_conf = personal_programs.get(program_choice, {})
        for k, v in prog_conf.items():
            cfg[k] = v

    # verrouillage
    program_selected = (st.session_state["selected_program_global"] != "Aucun")
    disabled = program_selected and not st.session_state["program_unlocked"]

    if program_selected:
        st.info(f"🔒 Programme sélectionné : **{st.session_state['selected_program_global']}** — protégé.")
        pwd = st.text_input("Entrez votre identifiant pour déverrouiller", type="password", key="pwd_params")
        if st.button("🔓 Déverrouiller", key="unlock_btn_params"):
            if pwd.strip() == user_id:
                st.session_state["program_unlocked"] = True
                st.success("✅ Programme déverrouillé.")
            else:
                st.session_state["program_unlocked"] = False
                st.error("❌ Identifiant incorrect.")
    else:
        st.info("Aucun programme sélectionné — modifications libres & création possible.")

    new_prog_name = st.text_input("Nom du nouveau programme (pour créer/mettre à jour)")

    if st.button("💾 Ajouter / Mettre à jour ce programme", key="save_prog_btn"):
        if program_selected and not st.session_state["program_unlocked"] and new_prog_name.strip() == "":
            st.warning("Ce programme est protégé — déverrouillez-le ou saisissez un **nouveau nom**.")
        else:
            # on sauvegarde TOUTES les valeurs actuelles du cfg
            to_save = cfg.copy()
            name = new_prog_name.strip() if new_prog_name.strip() else st.session_state["selected_program_global"]
            if name == "Aucun":
                st.warning("Donnez un nom de programme.")
            else:
                user_sessions.setdefault(user_id, {}).setdefault("programs", {})[name] = to_save
                user_sessions[user_id]["config"] = cfg.copy()
                save_json_atomic(USER_SESSIONS_FILE, user_sessions)
                set_selected_program(name)
                st.success(f"✅ Programme '{name}' sauvegardé & sélectionné.")

    # suppression
    st.markdown("**Gérer mes programmes personnels**")
    if personal_programs:
        del_choice = st.selectbox("Supprimer un programme", [""] + list(personal_programs.keys()), key="del_prog_sel")
        if st.button("🗑 Supprimer programme (Personnel)", key="del_prog_btn"):
            if del_choice and del_choice in user_sessions[user_id]["programs"]:
                del user_sessions[user_id]["programs"][del_choice]
                if st.session_state["selected_program_global"] == del_choice:
                    set_selected_program("Aucun")
                save_json_atomic(USER_SESSIONS_FILE, user_sessions)
                st.success(f"Programme '{del_choice}' supprimé.")
            else:
                st.error("Programme introuvable.")
    else:
        st.info("Aucun programme personnel pour l’instant.")

    # --- Paramètres d’injection & calculs ---
    st.markdown("---")
    st.subheader("💉 Paramètres d’injection et calculs")
    cfg["simultaneous_enabled"] = st.checkbox("Activer l'injection simultanée",
                                              value=cfg.get("simultaneous_enabled", False),
                                              disabled=disabled)
    if cfg["simultaneous_enabled"]:
        cfg["target_concentration"] = st.number_input("Concentration cible (mg I/mL)",
                                                      value=int(cfg.get("target_concentration", 350)),
                                                      min_value=200, max_value=500, step=10,
                                                      disabled=disabled)

    cfg["concentration_mg_ml"] = st.selectbox("Concentration (mg I/mL)",
                                              [300, 320, 350, 370, 400],
                                              index=[300, 320, 350, 370, 400].index(int(cfg.get("concentration_mg_ml", 350))),
                                              disabled=disabled)
    cfg["calc_mode"] = st.selectbox("Méthode de calcul",
                                    ["Charge iodée", "Surface corporelle", "Charge iodée sauf IMC > 30 → Surface corporelle"],
                                    index=["Charge iodée", "Surface corporelle", "Charge iodée sauf IMC > 30 → Surface corporelle"].index(cfg.get("calc_mode", "Charge iodée")),
                                    disabled=disabled)
    cfg["max_debit"] = st.number_input("Débit maximal autorisé (mL/s)",
                                       value=float(cfg.get("max_debit", 6.0)),
                                       min_value=1.0, max_value=20.0, step=0.1, disabled=disabled)

    # --- Acquisition & temps ---
    st.markdown("---")
    st.subheader("⏱ Départ d’acquisition et temps d’injection")
    cfg["auto_acquisition_by_age"] = st.checkbox("Ajuster automatiquement le départ d’acquisition selon l’âge",
                                                 value=bool(cfg.get("auto_acquisition_by_age", True)),
                                                 disabled=disabled)
    if not cfg["auto_acquisition_by_age"]:
        cfg["acquisition_start_param"] = st.number_input("Départ d’acquisition manuel (s)",
                                                         value=float(cfg.get("acquisition_start_param", 70.0)),
                                                         min_value=30.0, max_value=120.0, step=1.0, disabled=disabled)

    cfg["portal_time"] = st.number_input("Portal (s)", value=float(cfg.get("portal_time", 30.0)),
                                         min_value=5.0, max_value=120.0, step=1.0, disabled=disabled)
    cfg["arterial_time"] = st.number_input("Artériel (s)", value=float(cfg.get("arterial_time", 25.0)),
                                           min_value=5.0, max_value=120.0, step=1.0, disabled=disabled)

    cfg["intermediate_enabled"] = st.checkbox("Activer temps intermédiaire",
                                              value=bool(cfg.get("intermediate_enabled", False)), disabled=disabled)
    if cfg["intermediate_enabled"]:
        cfg["intermediate_time"] = st.number_input("Intermédiaire (s)",
                                                   value=float(cfg.get("intermediate_time", 28.0)),
                                                   min_value=5.0, max_value=120.0, step=1.0, disabled=disabled)

    # --- Rinçage & volumes ---
    cfg["rincage_volume"] = st.number_input("Volume rinçage (mL)",
                                            value=float(cfg.get("rincage_volume", 35.0)),
                                            min_value=10.0, max_value=100.0, step=1.0, disabled=disabled)
    cfg["rincage_delta_debit"] = st.number_input("Δ débit NaCl vs contraste (mL/s)",
                                                 value=float(cfg.get("rincage_delta_debit", 0.5)),
                                                 min_value=0.1, max_value=5.0, step=0.1, disabled=disabled)
    cfg["volume_max_limit"] = st.number_input("Plafond volume (mL) - seringue",
                                              value=float(cfg.get("volume_max_limit", 200.0)),
                                              min_value=50.0, max_value=500.0, step=10.0, disabled=disabled)

    # --- Charges iodées ---
    st.markdown("---")
    st.subheader("💊 Charges en iode par kV (g I/kg)")
    df_charges = pd.DataFrame({
        "kV": [80, 90, 100, 110, 120],
        "Charge (g I/kg)": [float(cfg["charges"].get(str(kv), 0.35)) for kv in [80, 90, 100, 110, 120]]
    })
    edited_df = st.data_editor(df_charges, num_rows="fixed", use_container_width=True, disabled=disabled)

    if st.button("💾 Sauvegarder les paramètres", key="save_params_btn", disabled=disabled):
        cfg["charges"] = {str(int(row.kV)): float(row["Charge (g I/kg)"]) for _, row in edited_df.iterrows()}
        set_cfg_and_persist(user_id, cfg)
        st.success("✅ Paramètres sauvegardés dans votre espace.")

    # --- Gestion identifiants ---
    st.markdown("---")
    st.subheader("🗂 Gestion des sessions / identifiants")
    all_user_ids = sorted(list(user_sessions.keys()))
    if user_id == SUPER_USER:
        st.markdown("**Super-utilisateur** : aperçu identifiants")
        st.dataframe(pd.DataFrame([{"identifiant": uid, "email": user_sessions[uid].get("email")} for uid in all_user_ids]),
                     use_container_width=True)
        del_input = st.text_input("Identifiant à supprimer (exact)", key="del_id_admin")
        if st.button("🗑 Supprimer identifiant (super-utilisateur)", key="del_id_btn"):
            target = del_input.strip()
            if not target:
                st.warning("Saisissez l'identifiant.")
            elif target == user_id:
                st.error("Impossible de supprimer l'identifiant connecté.")
            elif target not in user_sessions:
                st.error("Identifiant introuvable.")
            else:
                del user_sessions[target]
                save_json_atomic(USER_SESSIONS_FILE, user_sessions)
                st.success(f"Identifiant '{target}' supprimé.")
    else:
        st.markdown("Seul le super-utilisateur peut lister tous les identifiants.")
        del_input_self = st.text_input("Confirmez votre identifiant pour supprimer votre compte", key="del_self")
        if st.button("🗑 Supprimer MON identifiant", key="del_self_btn"):
            target = del_input_self.strip()
            if not target:
                st.warning("Saisissez votre identifiant exact.")
            elif target != user_id:
                st.error("Nom saisi différent de l'identifiant connecté.")
            else:
                if user_id in user_sessions:
                    del user_sessions[user_id]
                    save_json_atomic(USER_SESSIONS_FILE, user_sessions)
                st.session_state["accepted_legal"] = False
                st.session_state["user_id"] = None
                st.session_state["user_config"] = config_global.copy()
                set_selected_program("Aucun")
                st.success("Identifiant supprimé. Déconnecté.")
                st.rerun()

# =========================================================
# 🧍 Onglet Patient — sliders en haut + 3 blocs + synchro
# =========================================================
with tab_patient:
    # Style additionnel pour centrages radios & titres blocs
    st.markdown("""
        <style>
        div[data-testid="stSlider"] > label,
        div[data-testid="stSlider"] > label *,
        div[data-testid="stSelectbox"] > label,
        div[data-testid="stSelectbox"] > label * {
            display:block !important;
            width:100% !important;
            text-align:center !important;
            font-weight:700 !important;
            font-size:16px !important;
            color:#123A5F !important;
            margin-bottom:6px !important;
        }
        .section-title { font-size:22px; font-weight:700; color:#123A5F; margin-bottom:12px; text-align:center; }
        .block-title { text-align:center; font-weight:700; color:#123A5F; font-size:16px; margin-bottom:6px; }
        div[role="radiogroup"] { display:flex !important; justify-content:center !important; align-items:center !important; flex-wrap:nowrap !important; gap:4px !important; }
        div[role="radiogroup"] label { font-size:13px !important; padding:0 4px !important; margin:0 1px !important; white-space:nowrap !important; }
        .divider { border-left:1px solid #d9d9d9; height:100%; margin:0 10px; }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<div class='section-title'>🧍 Informations patient</div>", unsafe_allow_html=True)

    # Sliders + sélection programme (synchronisée)
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
        uid = st.session_state["user_id"]
        user_programs = user_sessions.get(uid, {}).get("programs", {})
        prog_list_patient = ["Aucun"] + list(user_programs.keys())
        idx_patient = prog_list_patient.index(st.session_state["selected_program_global"]) if st.session_state["selected_program_global"] in prog_list_patient else 0
        prog_choice_patient = st.selectbox("Sélection d'un programme",
                                           prog_list_patient,
                                           index=idx_patient,
                                           key="prog_patient_select")
        # synchro si changement
        if prog_choice_patient != st.session_state["selected_program_global"]:
            set_selected_program(prog_choice_patient)

        # charger config si programme choisi
        if prog_choice_patient != "Aucun":
            prog_conf = user_programs.get(prog_choice_patient, {})
            cfg_tmp = get_cfg()
            for k, v in prog_conf.items():
                cfg_tmp[k] = v
            set_cfg_and_persist(uid, cfg_tmp)
            user_sessions[uid]["last_selected_program"] = prog_choice_patient
            save_json_atomic(USER_SESSIONS_FILE, user_sessions)

    st.markdown("</div>", unsafe_allow_html=True)

    # Variables patient
    cfg = get_cfg()
    age = current_year - birth_year
    imc = weight / ((height / 100) ** 2)

    # 3 blocs
    col_left, col_div1, col_center, col_div2, col_right = st.columns([1.2, 0.05, 1.2, 0.05, 1.2])

    # Bloc gauche — Paramètres principaux
    with col_left:
        st.markdown("<div class='block-title'>Paramètres principaux</div>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([0.3, 1, 0.3])
        with c2:
            kv_scanner = st.radio("kV", [80, 90, 100, 110, 120], horizontal=True, index=4, key="kv_scanner_patient", label_visibility="collapsed")
        charge_iod = float(cfg.get("charges", {}).get(str(kv_scanner), 0.45))
        concentration = int(cfg.get("concentration_mg_ml", 350))
        calc_mode_label = cfg.get("calc_mode", "Charge iodée")
        st.markdown(
            f"<div style='text-align:center; font-size:15px; color:#123A5F;'>"
            f"<b>Charge iodée :</b> {charge_iod:.2f} g I/kg<br>"
            f"<b>Concentration :</b> {concentration} mg I/mL<br>"
            f"<b>Méthode :</b> {calc_mode_label}</div>",
            unsafe_allow_html=True,
        )

    with col_div1:
        st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    # Bloc centre — Injection & timing
    with col_center:
        st.markdown("<div class='block-title'>Injection et timing</div>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns([0.3, 1, 0.3])
        with c2:
            injection_modes = ["Portal", "Artériel"]
            if cfg.get("intermediate_enabled", False):
                injection_modes.append("Intermédiaire")
            injection_mode = st.radio("Mode d'injection", injection_modes, horizontal=True, index=0, key="injection_mode_patient", label_visibility="collapsed")

        if injection_mode == "Portal":
            base_time = float(cfg.get("portal_time", 30.0))
        elif injection_mode == "Artériel":
            base_time = float(cfg.get("arterial_time", 25.0))
        elif injection_mode == "Intermédiaire":
            base_time = float(cfg.get("intermediate_time", 28.0))
        else:
            base_time = float(cfg.get("portal_time", 30.0))

        acquisition_start = calculate_acquisition_start(age, cfg)
        st.markdown(
            f"<div style='text-align:center; font-size:15px; color:#123A5F;'>"
            f"<b>Temps {injection_mode.lower()} :</b> {base_time:.0f} s<br>"
            f"<b>Départ d'acquisition :</b> {acquisition_start:.1f} s"
            f"</div>",
            unsafe_allow_html=True,
        )

        # Alerte et édition temps intermédiaire (si activé)
        if injection_mode == "Intermédiaire":
            st.markdown(
                """
                <div style='background-color:#E3F2FD; border-left:4px solid #1976D2;
                            padding:8px 10px; margin-top:6px; border-radius:6px;
                            color:#0D47A1; font-size:13px; text-align:center;'>
                    ⚠️ <b>Attention :</b> pensez à ajuster le départ d’acquisition.
                </div>
                """,
                unsafe_allow_html=True
            )
            if cfg.get("intermediate_enabled", False):
                new_intermediate_time = st.number_input("Modifier temps intermédiaire (s)",
                                                        value=float(cfg.get("intermediate_time", 28.0)),
                                                        min_value=5.0, max_value=120.0, step=1.0,
                                                        key="patient_intermediate_time")
                cfg["intermediate_time"] = float(new_intermediate_time)
                set_cfg_and_persist(st.session_state["user_id"], cfg)

    with col_div2:
        st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    # Bloc droit — Options avancées (état seulement)
    with col_right:
        st.markdown("<div class='block-title'>Options avancées</div>", unsafe_allow_html=True)
        auto_age = bool(cfg.get("auto_acquisition_by_age", True))
        sim_enabled = bool(cfg.get("simultaneous_enabled", False))
        st.markdown(
            f"<div style='text-align:center; font-size:15px; color:#123A5F;'>"
            f"<b>Ajustement automatique selon l'âge :</b><br>"
            f"{'✅ activé' if auto_age else '❌ désactivé'}<br><br>"
            f"<b>Injection simultanée :</b><br>"
            f"{'✅ activée' if sim_enabled else '❌ désactivée'}</div>",
            unsafe_allow_html=True,
        )

    # Calculs finaux
    volume, bsa = calculate_volume(
        weight, height, kv_scanner,
        float(cfg.get("concentration_mg_ml", 350)),
        imc, cfg.get("calc_mode", "Charge iodée"),
        cfg.get("charges", {}),
        float(cfg.get("volume_max_limit", 200.0))
    )
    injection_rate, injection_time, time_adjusted = adjust_injection_rate(
        volume, float(base_time), float(cfg.get("max_debit", 6.0))
    )

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

# =========================================================
# 📘 Onglet Tutoriel (inchangé)
# =========================================================
with tab_tutorial:
    st.title("📘 Tutoriel — Mode d'emploi et principes cliniques")
    st.header("🔧 Guide pas à pas — Utilisation")
    st.markdown("""
    1. **Patient** : saisissez poids, taille et année de naissance.
    2. **kV du scanner** : choisissez la valeur correspondant à votre machine.
    3. **Mode d’injection** : Portal / Artériel / Intermédiaire.
    4. **Paramètres** : vérifiez la concentration, le débit max et les temps.
    5. **Injection simultanée** : si activée, définissez la concentration cible.
    6. **Validation** : relisez les résultats (volume contraste, NaCl, débit).
    """)
    st.header("🧠 Explications techniques et cliniques")
    st.markdown("""
    - **Charge iodée** : dose proportionnelle au poids.
    - **Surface corporelle (BSA)** : dose selon m².
    - **IMC>30** : règle “Charge iodée sauf IMC>30 → Surface corporelle”.
    - **Débit** = volume / temps; ajusté si dépasse max.
    - **Injection simultanée** : dilution pour atteindre une concentration cible.
    """)

# ------------------------
# Footer
# ------------------------
st.markdown(f"""<div style='text-align:center; margin-top:20px; font-size:0.8rem; color:#666;'>
© 2025 Guerbet | Développé par <b>Sébastien Partouche</b><br>
Calculette de dose de produit de contraste en oncologie adulte.<br>
<div style='display:inline-block; background-color:#FCE8B2; border:1px solid #F5B800; padding:8px 15px; border-radius:10px; color:#5A4500; font-weight:600; margin-top:10px;'>🧪 Version BETA TEST – Usage interne / évaluation</div>
</div>""", unsafe_allow_html=True)
