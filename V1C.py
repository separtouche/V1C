# -*- coding: utf-8 -*-
# Calculette de dose de produit de contraste en oncologie chez l'adulte
# Version commentée et avec onglet Tutoriel (mixte : pas-à-pas + technique)
# Auteur : adapté pour Sébastien Partouche
# Usage : streamlit run app.py

import streamlit as st             # framework web léger pour créer des interfaces interactives
import json                        # pour lire / écrire les fichiers de configuration JSON
import os                          # pour opérations système (existence de fichiers)
import pandas as pd                # pour manipulation de tableaux (DataFrame)
import math                        # pour calculs mathématiques (racine carrée)
import base64                      # pour convertir images en base64 (affichage inline)
from datetime import datetime      # pour récupérer l'année courante (calcul âge)

# ===================== Styles =====================
# Couleurs et dimensions utilisées pour l'UI — variables pour facilité de maintenance
GUERBET_BLUE = "#124F7A"           # couleur bleu corporate pour l'en-tête
CARD_BG = "#EAF1F8"                # fond des cartes de résultat
CARD_HEIGHT = "150px"              # hauteur minimum des cartes

# Configuration de la page Streamlit (titre onglet + icône + mise en page)
st.set_page_config(page_title="Calculette de dose de produit de contraste en oncologie (adulte)", page_icon="💉", layout="wide")

# Injection de CSS inline pour personnaliser l'apparence de l'application
# Le CSS gère l'en-tête, les cartes de résultat, sections de paramètres, etc.
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
    min-height: {CARD_HEIGHT};
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
.result-card div.sub-item {{ margin-top:4px; font-size:0.9rem; }}
.result-card div.sub-item-large {{ margin-top:6px; font-size:1.1rem; font-weight:600; }}
.param-section {{
    background: #ffffff;
    border-radius: 10px;
    padding: 16px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    margin-bottom: 12px;
}}
</style>
""", unsafe_allow_html=True)

# ===================== Fichiers =====================
# Noms de fichiers de configuration et bibliothèque
CONFIG_FILE = "iodine_config.json"  # fichier pour stocker paramètres persistants
LIB_FILE = "libraries.json"         # fichier pour stocker programmes enregistrés (bibliothèque)

# Valeurs par défaut (utilisées si aucun fichier de config n'existe)
# Contient : charges par kV, concentration cible, temps, options, etc.
default_config = {
    # charges iodées par kV (g I/kg) converties en str keys pour compatibilité JSON
    "charges": {str(kv): val for kv, val in zip([80,90,100,110,120],[0.35,0.38,0.40,0.42,0.45])},
    "concentration_mg_ml": 350,      # concentration produit contraste par défaut (mg I/mL)
    "portal_time": 30.0,             # temps portal par défaut (s)
    "arterial_time": 25.0,           # temps artériel par défaut (s)
    "intermediate_enabled": False,   # flag pour activer temps intermédiaire
    "intermediate_time": 28.0,       # temps intermédiaire par défaut (s)
    "acquisition_start_param": 70.0, # paramètre par défaut pour départ d'acquisition
    "auto_acquisition_by_age": True, # activer réglage départ d'acquisition automatique selon âge
    "max_debit": 6.0,                # débit max autorisé (mL/s)
    "rincage_volume": 35.0,          # volume rinçage par défaut (mL)
    "rincage_delta_debit": 0.5,      # différence débit NaCl vs contraste (mL/s)
    "calc_mode": "Charge iodée",     # mode de calcul par défaut
    "simultaneous_enabled": False,   # injection simultanée désactivée par défaut
    "target_concentration": 350      # concentration cible lors d'injection simultanée
}

# ===================== Charger config et bibliothèque =====================
# Charger la config si fichier existe sinon utiliser default_config
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)    # lecture JSON du fichier de configuration
    except:
        # En cas d'erreur de lecture, retomber sur les valeurs par défaut
        config = default_config.copy()
else:
    # Si aucun fichier, on initialise avec la configuration par défaut
    config = default_config.copy()

# Charger la bibliothèque de programmes si fichier existe sinon initialiser vide
if os.path.exists(LIB_FILE):
    try:
        with open(LIB_FILE, "r") as f:
            libraries = json.load(f)  # lecture JSON de la bibliothèque
    except:
        libraries = {"programs": {}} # structure minimale si lecture échoue
else:
    libraries = {"programs": {}}     # structure minimale si fichier absent

# S'assurer que la clé "programs" existe dans la structure libraries
if "programs" not in libraries:
    libraries["programs"] = {}

# ===================== Fonctions =====================
# Fonctions utilitaires et fonctions métiers avec commentaires cliniques

def save_config(data):
    """Sauvegarde la configuration dans CONFIG_FILE (JSON prettified)."""
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

def save_libraries(data):
    """Sauvegarde la bibliothèque de programmes dans LIB_FILE (JSON prettified)."""
    with open(LIB_FILE, "w") as f:
        json.dump(data, f, indent=4)

def delete_program(name):
    """Supprime un programme de la bibliothèque si présent et sauvegarde."""
    if name in libraries.get("programs", {}):
        del libraries["programs"][name]
        save_libraries(libraries)
        st.success(f"Programme '{name}' supprimé !")

def calculate_bsa(weight, height):
    """
    Calcul de la surface corporelle (BSA) selon formule de DuBois simplifiée :
    BSA (m²) ≈ sqrt( (taille_cm * poids_kg) / 3600 )
    utilisé pour adapter la dose en fonction de la surface corporelle.
    """
    return math.sqrt((height * weight) / 3600)

def calculate_volume(weight, height, kv, concentration, imc, calc_mode, charges):
    """
    Calcul du volume de contraste nécessaire.
    - Si mode 'Surface corporelle' OU (mode 'Charge iodée sauf...' ET IMC >= 30) :
        -> Utilise BSA * facteur_kV / (concentration en g/mL)
    - Sinon (mode 'Charge iodée') :
        -> volume = poids * charge_iodée (g I/kg) / (concentration en g/mL)
    Retourne (volume_limite, bsa) où volume_limite est plafonné à 200 mL.
    Notes :
    - concentration param est en mg I/mL, on convertit en g I/mL en divisant par 1000.
    - kv_factors : facteurs empiriques utilisés pour la méthode BSA (valeurs cliniques).
    """
    # Facteurs empiriques dépendant du kV du scanner (valeurs choisies pour l'exemple)
    kv_factors = {80: 11, 90: 13, 100: 15, 110: 16.5, 120: 18.6}

    # Choix de la méthode selon calc_mode et IMC
    if calc_mode == "Surface corporelle" or (calc_mode.startswith("Charge iodée sauf") and imc >= 30):
        # Calculer BSA puis volume selon facteur kV
        bsa = calculate_bsa(weight, height)
        factor = kv_factors.get(kv, 15)
        # concentration (mg/mL) -> (g/mL) : /1000
        volume = bsa * factor / (concentration / 1000)
    else:
        # Mode "Charge iodée" standard : dose proportionnelle au poids
        # Récupérer la charge en g I / kg (clé string)
        charge_iodine = float(charges.get(str(kv), 0.4))
        volume = weight * charge_iodine / (concentration / 1000)
        bsa = None

    # Plafonner le volume pour des raisons de sécurité / limites matérielles (ex: seringue)
    return min(volume, 200.0), bsa

def calculate_acquisition_start(age, cfg):
    """
    Détermine le départ d'acquisition (en s) en fonction de l'âge si auto_acquisition_by_age activé.
    - si auto_acquisition_by_age False -> retourne acquisition_start_param (valeur par défaut).
    - si age < 70 -> valeur par défaut (ex : 70s).
    - si 70 <= age <= 90 -> on utilise l'âge comme départ (stratégie clinique arbitraire).
    - si age > 90 -> on plafonne à 90s.
    Cette logique reflète une stratégie pour adapter l'acquisition selon fragilité / contraste.
    """
    if not cfg.get("auto_acquisition_by_age", True):
        return float(cfg.get("acquisition_start_param", 70.0))
    if age < 70:
        return float(cfg.get("acquisition_start_param", 70.0))
    elif 70 <= age <= 90:
        return float(age)
    else:
        return 90.0

def adjust_injection_rate(volume, injection_time, max_debit):
    """
    Calcule le débit d'injection (mL/s) = volume (mL) / temps (s).
    Si le débit calculé dépasse max_debit, on ajuste le temps pour respecter max_debit.
    Retourne : (injection_rate_mL_s, injection_time_s_apres_ajustement, time_adjusted_bool)
    """
    injection_rate = volume / injection_time if injection_time > 0 else 0.0
    time_adjusted = False
    if injection_rate > max_debit:
        # Réajuster le temps pour respecter le débit maximal autorisé
        injection_time = volume / max_debit
        injection_rate = max_debit
        time_adjusted = True
    return float(injection_rate), float(injection_time), bool(time_adjusted)

def img_to_base64(path):
    """Convertit une image locale en chaîne base64 pour affichage inline HTML."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

# ===================== Session init =====================
# Initialiser des clés dans st.session_state si absentes (prévenir KeyError)
for key in ["accepted_legal", "selected_program"]:
    if key not in st.session_state:
        st.session_state[key] = config.get(key)

# ===================== Header =====================
# Chemin vers le logo (optionnel). Si présent, on l'affiche dans l'en-tête.
logo_path = "guerbet_logo.png"
if os.path.exists(logo_path):
    # Convertir l'image en base64 et l'injecter dans l'HTML du header
    img_b64 = img_to_base64(logo_path)
    st.markdown(f"""
    <div class="header-banner">
      <img src="data:image/png;base64,{img_b64}" class="header-logo" alt="Guerbet logo" />
      <div class="header-title">Calculette de dose de produit de contraste en oncologie chez l'adulte</div>
    </div>
    """, unsafe_allow_html=True)
else:
    # Si pas de logo, afficher seulement le titre dans l'en-tête
    st.markdown(f"<div class='header-banner'><div class='header-title'>Calculette de dose de produit de contraste en oncologie chez l'adulte</div></div>", unsafe_allow_html=True)

# ===================== Mentions légales =====================
# Afficher et forcer l'acceptation des mentions légales avant d'utiliser l'outil
if not st.session_state["accepted_legal"]:
    st.markdown("### Mentions légales — acceptation requise")
    st.markdown(
        "Avant d'utiliser cet outil, vous devez accepter la mention légale et les conditions d'utilisation. "
        "Les données et résultats proposés par cette calculette sont à titre indicatif et doivent être validés par un professionnel de santé. "
        "Cet outil est spécifiquement destiné à un usage en oncologie adulte ; il ne s'applique pas aux enfants ou aux situations pédiatriques."
    )
    # case à cocher pour valider la lecture des mentions légales
    accept = st.checkbox("✅ J’accepte les mentions légales.", key="accept_checkbox")
    # bouton pour confirmer l'acceptation (nécessaire si coché)
    if st.button("Accepter et continuer"):
        if accept:
            st.session_state["accepted_legal"] = True
        else:
            st.warning("Vous devez cocher la case pour accepter.")
    # stoppe l'exécution si non accepté
    st.stop()

# ===================== Onglets =====================
# Créer trois onglets : Patient, Paramètres, Tutoriel (mixte)
tab_patient, tab_params, tab_tutorial = st.tabs(["🧍 Patient", "⚙️ Paramètres", "📘 Tutoriel"])

# ===================== Onglet Paramètres =====================
with tab_params:
    # En-tête de la section paramètres
    st.header("⚙️ Paramètres et Bibliothèque")
    st.subheader("💉 Injection simultanée")

    # Checkbox pour activer/désactiver l'injection simultanée
    config["simultaneous_enabled"] = st.checkbox("Activer l'injection simultanée", value=config.get("simultaneous_enabled", False))
    # Si activé, permettre de définir la concentration cible (mg I/mL)
    if config["simultaneous_enabled"]:
        config["target_concentration"] = st.number_input("Concentration cible (mg I/mL)", value=config.get("target_concentration",350), min_value=300, max_value=400, step=10)

    # Bibliothèque de programmes (CRUD basique) : sélection, ajout/màj, suppression
    st.subheader("📚 Bibliothèque de programmes")
    program_choice = st.selectbox("Programme", ["Aucun"] + list(libraries.get("programs", {}).keys()))
    if program_choice != "Aucun":
        # Si un programme est sélectionné, charger sa configuration dans 'config' pour préremplir
        prog_conf = libraries["programs"].get(program_choice, {})
        for key, val in prog_conf.items():
            config[key] = val

    # Entrée pour nom du nouveau programme
    new_prog_name = st.text_input("Nom du nouveau programme")
    # Bouton pour ajouter ou mettre à jour un programme dans la bibliothèque
    if st.button("💾 Ajouter/Mise à jour programme"):
        if new_prog_name.strip():
            # On enregistre toutes les clés de config sauf celles liées uniquement à l'UI
            libraries["programs"][new_prog_name.strip()] = {k: config[k] for k in config if k not in ["simultaneous_enabled", "target_concentration"]}
            save_libraries(libraries)
            st.success(f"Programme '{new_prog_name}' ajouté/mis à jour !")

    # Si la bibliothèque contient des programmes, afficher option de suppression
    if libraries.get("programs"):
        del_prog = st.selectbox("Supprimer un programme", [""] + list(libraries["programs"].keys()))
        if st.button("🗑 Supprimer programme"):
            if del_prog:
                delete_program(del_prog)

    # Paramètres globaux de l'application modifiables par l'utilisateur
    st.subheader("⚙️ Paramètres globaux")
    # Concentration disponible (liste prédéfinie)
    config["concentration_mg_ml"] = st.selectbox("Concentration (mg I/mL)", [300,320,350,370,400], index=[300,320,350,370,400].index(int(config.get("concentration_mg_ml",350))))
    # Mode de calcul (Charge iodée vs Surface corporelle vs exception IMC)
    config["calc_mode"] = st.selectbox("Méthode de calcul", ["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"], index=["Charge iodée","Surface corporelle","Charge iodée sauf IMC > 30 → Surface corporelle"].index(config.get("calc_mode","Charge iodée")))
    # Débit maximal autorisé (contrainte matériel / sécurité)
    config["max_debit"] = st.number_input("Débit maximal autorisé (mL/s)", value=float(config.get("max_debit",6.0)), min_value=1.0, max_value=20.0, step=0.1)
    # Temps portal (s)
    config["portal_time"] = st.number_input("Portal (s)", value=float(config.get("portal_time",30.0)), min_value=5.0, max_value=120.0, step=1.0)
    # Temps artériel (s)
    config["arterial_time"] = st.number_input("Artériel (s)", value=float(config.get("arterial_time",25.0)), min_value=5.0, max_value=120.0, step=1.0)
    # Activer temps intermédiaire (option)
    config["intermediate_enabled"] = st.checkbox("Activer temps intermédiaire", value=bool(config.get("intermediate_enabled",False)))
    # Si le temps intermédiaire est activé, permet de le régler
    if config["intermediate_enabled"]:
        config["intermediate_time"] = st.number_input("Intermédiaire (s)", value=float(config.get("intermediate_time",28.0)), min_value=5.0, max_value=120.0, step=1.0)
    # Volume de rinçage (mL)
    config["rincage_volume"] = st.number_input("Volume de rinçage (mL)", value=float(config.get("rincage_volume",35.0)), min_value=10.0, max_value=100.0, step=1.0)
    # Différence débit NaCl vs contraste (mL/s)
    config["rincage_delta_debit"] = st.number_input("Différence débit NaCl vs contraste (mL/s)", value=float(config.get("rincage_delta_debit",0.5)), min_value=0.1, max_value=5.0, step=0.1)

    # Affichage et édition des charges iodées par kV via DataFrame éditable
    st.markdown("**Charges en iode par kV (g I/kg)**")
    df_charges = pd.DataFrame({
        "kV":[80,90,100,110,120],
        "Charge (g I/kg)":[float(config["charges"].get(str(kv),0.35)) for kv in [80,90,100,110,120]]
    })
    # Data editor permet modification directe en UI
    edited_df = st.data_editor(df_charges, num_rows="fixed", use_container_width=True)
    # Bouton pour sauvegarder les paramètres modifiés
    if st.button("💾 Sauvegarder les paramètres"):
        try:
            # Reconstruire dictionnaire charges depuis le DataFrame édité
            config["charges"] = {str(int(row.kV)): float(row["Charge (g I/kg)"]) for _,row in edited_df.iterrows()}
            save_config(config)   # sauvegarde sur disque
            st.success("✅ Paramètres sauvegardés !")
        except Exception as e:
            # Afficher erreur en cas de problème (ex : valeur non numérique)
            st.error(f"Erreur lors de la sauvegarde : {e}")

# ===================== Onglet Patient =====================
with tab_patient:
    # Titre de la section patient (spécifié pour oncologie adulte)
    st.header("🧍 Informations patient (adulte en oncologie)")

    # Trois colonnes pour poids, taille et année de naissance
    col_w, col_h, col_birth = st.columns([1,1,1])
    with col_w:
        # Slider pour le poids (20 à 200 kg)
        weight = st.select_slider("Poids (kg)", options=list(range(20,201)), value=70)
    with col_h:
        # Slider pour la taille (100 à 220 cm)
        height = st.select_slider("Taille (cm)", options=list(range(100,221)), value=170)
    with col_birth:
        # Slider pour l'année de naissance (plage 120 ans en arrière)
        current_year = datetime.now().year
        birth_year = st.select_slider("Année de naissance", options=list(range(current_year-120,current_year+1)), value=current_year-40)

    # Calcul de l'âge à partir de l'année de naissance
    age = current_year - birth_year
    # Calcul de l'IMC : poids (kg) / (taille (m))^2
    imc = weight / ((height/100)**2)

    # Colonnes pour kV et choix du mode + temps
    col_kv, col_mode_time = st.columns([1.2,2])
    with col_kv:
        # radio pour choisir le kV du scanner (valeurs usuelles)
        kv_scanner = st.radio("kV du scanner", [80,90,100,110,120], index=4, horizontal=True)

    with col_mode_time:
        # Colonnes imbriquées : mode (Portal/Artériel/Intermédiaire) et affichage du temps correspondant
        col_mode, col_times = st.columns([1.2,1])
        with col_mode:
            # Construire la liste des modes disponibles selon activation du temps intermédiaire
            injection_modes = ["Portal","Artériel"]
            if config.get("intermediate_enabled",False):
                injection_modes.append("Intermédiaire")
            # radio pour le mode d'injection (horizontal)
            injection_mode = st.radio("Mode d’injection", injection_modes, horizontal=True)

        with col_times:
            # --- Afficher uniquement le temps corrélé au mode sélectionné ---
            # Si Portal choisi : temps fixe portal depuis config
            if injection_mode == "Portal":
                base_time = float(config.get("portal_time",30.0))
            # Si Artériel choisi : temps fixe artériel depuis config
            elif injection_mode == "Artériel":
                base_time = float(config.get("arterial_time",25.0))
            # Si Intermédiaire choisi : entrée modifiable par l'utilisateur
            else:  # Intermédiaire
                base_time = st.number_input(
                    "Temps Intermédiaire (s)",
                    value=float(config.get("intermediate_time",28.0)),
                    min_value=5.0, max_value=120.0, step=1.0
                )

            # Afficher uniquement la ligne du temps en rapport avec le mode sélectionné
            st.markdown(f"**Temps {injection_mode} :** {base_time:.0f} s")
            # Calcul du départ d'acquisition (fonction métier)
            acquisition_start = calculate_acquisition_start(age, config)
            # Affichage du départ d'acquisition
            st.markdown(f"**Départ d'acquisition :** {acquisition_start:.1f} s")
            # Affichage de la concentration choisie
            st.markdown(f"**Concentration :** {int(config.get('concentration_mg_ml',350))} mg I/mL")

    # ========== Calculs principaux ==========
    # Calcul du volume de contraste en mL et éventuellement de la BSA (m²)
    volume, bsa = calculate_volume(
        weight,
        height,
        kv_scanner,
        float(config.get("concentration_mg_ml",350)),
        imc,
        config.get("calc_mode","Charge iodée"),
        config.get("charges",{})
    )

    # Calcul du débit d'injection et ajustement si dépassement du débit max autorisé
    injection_rate, injection_time, time_adjusted = adjust_injection_rate(
        volume,
        float(base_time),
        float(config.get("max_debit",6.0))
    )

    # ========== Gestion Injection Simultanée (si activée) ==========
    if config.get("simultaneous_enabled", False):
        # target concentration souhaitée pour le mélange contraste + NaCl
        target = config.get("target_concentration", 350)
        # volume de produit de contraste réel nécessaire après dilution
        vol_contrast = volume * target / config.get("concentration_mg_ml",350)
        # volume de NaCl ajouté pour obtenir la dilution (mL)
        vol_nacl_dilution = volume - vol_contrast
        # pourcentages pour affichage utilisateur
        perc_contrast = vol_contrast / volume * 100
        perc_nacl_dilution = vol_nacl_dilution / volume * 100

        # Texte HTML pour affichage de la dilution et du rinçage
        contrast_text = f"{vol_contrast:.1f} mL ({perc_contrast:.0f}%)"
        nacl_rincage_volume = config.get("rincage_volume",35.0)
        # calcul du débit de rinçage NaCl : on soustrait un delta pour obtenir débit légèrement inférieur
        nacl_rincage_debit = max(0.1, injection_rate - config.get("rincage_delta_debit",0.5))
        nacl_text = f"<div class='sub-item-large'>Dilution : {vol_nacl_dilution:.1f} mL ({perc_nacl_dilution:.0f}%)</div>"
        nacl_text += f"<div class='sub-item-large'>Rinçage : {nacl_rincage_volume:.1f} mL @ {nacl_rincage_debit:.1f} mL/s</div>"
    else:
        # Si injection simple (non simultanée) : volume contraste = volume calculé
        vol_contrast = volume
        contrast_text = f"{vol_contrast:.1f} mL"
        # texte simple pour le volume de rinçage
        nacl_text = f"{config.get('rincage_volume',35.0):.0f} mL"

    # ========== Affichage des résultats sous forme de cartes ==========
    col_contrast, col_nacl, col_rate = st.columns(3, gap="medium")
    with col_contrast:
        # Carte volume contraste
        st.markdown(f"""<div class="result-card"><h3>💧 Volume contraste conseillé</h3><h1>{contrast_text}</h1></div>""", unsafe_allow_html=True)
    with col_nacl:
        # Carte volume NaCl ou informations dilution + rinçage si simultané
        st.markdown(f"""<div class="result-card"><h3>💧 Volume NaCl conseillé</h3><h1>{nacl_text}</h1></div>""", unsafe_allow_html=True)
    with col_rate:
        # Carte débit conseillé (mL/s)
        st.markdown(f"""<div class="result-card"><h3>🚀 Débit conseillé</h3><h1>{injection_rate:.1f} mL/s</h1></div>""", unsafe_allow_html=True)

    # Si le temps a été ajusté pour respecter le débit maximal, afficher un avertissement
    if time_adjusted:
        st.warning(f"⚠️ Le temps d’injection a été ajusté à {injection_time:.1f}s pour respecter le débit maximal de {config.get('max_debit',6.0)} mL/s.")

    # Affichage des informations complémentaires : IMC et BSA si disponible
    st.info(f"📏 IMC : {imc:.1f}" + (f" | Surface corporelle : {bsa:.2f} m²" if bsa else ""))

    # Avertissement légal / usage clinique (rappel important)
    st.markdown("""<div style='background-color:#FCE8E6; color:#6B1A00; padding:10px; border-radius:8px; margin-top:15px; font-size:0.9rem;'>⚠️ <b>Avertissement :</b> Ce logiciel est un outil d’aide à la décision. Les résultats sont <b>indicatifs</b> et doivent être validés par un professionnel de santé. Destiné uniquement aux patients adultes en oncologie.</div>""", unsafe_allow_html=True)

# ===================== Onglet Tutoriel (mixte) =====================
with tab_tutorial:
    # Titre et introduction
    st.title("📘 Tutoriel — Mode d'emploi et principes cliniques")
    st.markdown("Bienvenue dans le tutoriel. Cette section explique **comment utiliser** la calculette (pas-à-pas) et **pourquoi** chaque calcul est effectué (explication technique).")

    # Section 1 : Guide pas à pas (utilisation)
    st.header("🔧 Guide pas à pas — Utilisation")
    st.markdown("""
    1. **Patient** : saisissez le poids (kg), la taille (cm) et l'année de naissance. L'IMC et l'âge sont calculés automatiquement.  
    2. **kV du scanner** : choisissez la valeur correspondant à votre machine (80–120 kV).  
    3. **Mode d’injection** : choisissez `Portal`, `Artériel` ou `Intermédiaire`. Seul le temps correspondant est affiché et utilisé pour le calcul.  
    4. **Paramètres** : vérifiez la concentration du produit (mg I/mL), le débit max autorisé et les temps (Paramètres → ⚙️).  
    5. **Injection simultanée** : si activée, définissez la concentration cible — l'outil calcule la dilution contraste/NaCl et les volumes de rinçage.  
    6. **Validation** : relisez les résultats (volume contraste, volume NaCl, débit). Les valeurs sont indicatives : **validez toujours cliniquement** avant administration.
    """)

    # Section 2 : Explications techniques / cliniques
    st.header("🧠 Explications techniques et principes cliniques")
    st.markdown("#### A. Charge iodée vs Surface corporelle")
    st.markdown("""
    - **Charge iodée (g I/kg)** : méthode classique où la dose d'iode est proportionnelle au poids du patient.  
      Exemple : 0.4 g I/kg => volume = poids * 0.4 / (concentration g I/mL).  
      Utile pour standardiser la quantité d'iode administrée.
    - **Surface corporelle (BSA)** : utilisée lorsque l'on veut doser selon la surface corporelle (m²) plutôt que le poids, souvent plus pertinente pour certains protocoles oncologiques.  
      BSA est calculée approximativement par : `sqrt( (taille_cm * poids_kg) / 3600 )`.
    - **Règle IMC** : l'option « Charge iodée sauf IMC > 30 → Surface corporelle » permet d'éviter la surdose chez les patients obèses en utilisant la BSA si IMC ≥ 30.
    """)

    st.markdown("#### B. Débit d'injection et temps")
    st.markdown("""
    - **Débit (mL/s)** = volume total / temps d'injection (s).  
    - **Limite du débit** : si le débit calculé dépasse le débit maximal autorisé (matériel / sécurité), l'outil **augmente le temps** d'injection pour respecter le débit maximal.  
    - **Choix du temps** : la calculette affiche **uniquement** le temps correspondant au mode d'injection sélectionné (Portal / Artériel / Intermédiaire).
    """)

    st.markdown("#### C. Injection simultanée (Dilution avec NaCl)")
    st.markdown("""
    - Lorsque l'injection simultanée est activée, on vise une **concentration cible** (mg I/mL) finale.  
    - Le calcul fractionne le volume final entre **produit contraste** et **NaCl** :
      - `vol_contrast = volume_total * (concentration_cible / concentration_initiale)`  
      - `vol_NaCl = volume_total - vol_contrast`
    - Avantages cliniques : permet de réduire la viscosité du bolus, optimiser la concentration d'iode, ou adapter à des seringues/contrainte d'administration.
    - Pensez au **rinçage NaCl** pour pousser le contraste dans la veine et limiter les résidus dans la ligne intraveineuse.
    """)

    st.markdown("#### D. Points de sécurité et bonnes pratiques")
    st.markdown("""
    - **Toujours** vérifier l'identité du patient et les antécédents (insuffisance rénale, allergies, antécédents de réactions au produit de contraste).  
    - Vérifier la **concentration réelle** du flacon de contraste (mg I/mL) et la correspondre dans l'outil.  
    - Ne dépassez pas le **volume de seringue** et la capacité d'administration du matériel.  
    - Cette calculette ne remplace pas le jugement clinique : les résultats sont **indicatifs**.
    """)

    # Section 3 : Explication des fonctions du code (court résumé pour développeurs)
    st.header("💻 Explication des fonctions du code (pour développeurs)")
    st.markdown("""
    - `calculate_bsa(weight, height)` : calcule la surface corporelle (BSA).  
    - `calculate_volume(...)` : calcule le volume nécessaire selon le mode (charge iodée ou BSA) et applique un plafond à 200 mL.  
    - `calculate_acquisition_start(age, cfg)` : ajuste le départ d'acquisition selon l'âge si l'option auto est activée.  
    - `adjust_injection_rate(volume, injection_time, max_debit)` : calcule le débit et ajuste le temps si nécessaire pour respecter `max_debit`.  
    - Gestion de la **bibliothèque** : permet d'enregistrer/charger des programmes (JSON) via `libraries.json`.
    - UI : `st.data_editor` permet d'éditer les charges iodées par kV de façon interactive.
    """)

    # Section 4 : Exemple de workflow clinique (cas d'usage)
    st.header("🩺 Exemple de workflow clinique")
    st.markdown("""
    **Cas** : patient adulte 75 kg, 170 cm, kV=120, mode Portal, concentration 350 mg I/mL.  
    1. Saisir poids/taille/année de naissance.  
    2. Vérifier kV = 120.  
    3. Choisir mode Portal -> temps = 30 s (ou celui fixé dans Paramètres).  
    4. Lire volume contraste conseillé et débit.  
    5. Si injection simultanée activée, vérifier dilution et volume NaCl pour préparation de seringue.
    """)

    # Option : lien vers documentation ou PDF si l'utilisateur veut une fiche imprimable
    st.markdown("🔗 **Astuce** : pour une fiche imprimable, tu peux copier-coller le contenu du tutoriel dans un document ou je peux t'aider à générer un PDF exportable si tu le souhaites.")

# ===================== Footer =====================
# Footer global avec copyright et info version
st.markdown(f"""<div style='text-align:center; margin-top:20px; font-size:0.8rem; color:#666;'>
© 2025 Guerbet | Développé par <b>Sébastien Partouche</b><br>
Calculette de dose de produit de contraste en oncologie — usage adulte uniquement.<br>
<div style='display:inline-block; background-color:#FCE8B2; border:1px solid #F5B800; padding:8px 15px; border-radius:10px; color:#5A4500; font-weight:600; margin-top:10px;'>🧪 Version BETA TEST – Usage interne / évaluation</div>
</div>""", unsafe_allow_html=True)
