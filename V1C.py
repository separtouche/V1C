# ------------------------
# Onglet Patient (version sans fond blanc, blocs remontés)
# ------------------------
with tab_patient:
    # CSS ajusté : suppression du fond blanc et remontée légère des blocs
    st.markdown("""
        <style>
        .slider-red .stSlider [data-baseweb="slider"] div[role="slider"] { background-color: #E53935 !important; }
        .slider-red .stSlider [data-baseweb="slider"] div[role="slider"]::before { background-color: #E53935 !important; }
        .divider { border-left: 1px solid #d9d9d9; height: 100%; margin: 0 20px; }
        .section-title { font-size: 22px; font-weight: 700; color:#123A5F; margin-bottom: 10px; }
        div[role="radiogroup"] label { padding: 2px 6px !important; margin: 0 2px !important; font-size: 0.85rem !important; }
        .top-group { margin-top: -15px; }  /* remonte légèrement les blocs */
        </style>
    """, unsafe_allow_html=True)

    st.markdown("<div class='section-title'>🧍 Informations patient (adulte en oncologie)</div>", unsafe_allow_html=True)

    # === LIGNE 1 : Trois blocs (remontés, sans fond blanc) ===
    st.markdown("<div class='top-group'>", unsafe_allow_html=True)
    col_left, col_div1, col_center, col_div2, col_right = st.columns([1.2, 0.05, 1.2, 0.05, 1.2])

    # 🧭 Bloc gauche : KV, charge iodée, concentration, méthode utilisée
    with col_left:
        st.markdown("**Paramètres principaux**")
        kv_scanner = st.radio(
            "kV",
            [80, 90, 100, 110, 120],
            horizontal=True,
            index=4,
            key="kv_scanner_patient",
            label_visibility="collapsed"
        )
        charge_iod = float(cfg.get("charges", {}).get(str(kv_scanner), 0.45))
        concentration = int(cfg.get("concentration_mg_ml", 350))
        calc_mode_label = cfg.get("calc_mode", "Charge iodée")

        st.markdown(
            f"<div style='text-align:center; margin-top:6px;'>"
            f"<b>Charge iodée :</b> {charge_iod:.2f} g I/kg<br>"
            f"<b>Concentration :</b> {concentration} mg I/mL<br>"
            f"<b>Méthode :</b> {calc_mode_label}"
            f"</div>",
            unsafe_allow_html=True
        )

    with col_div1:
        st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    # 💉 Bloc centre : mode d'injection, temps d'injection, départ d'acquisition
    with col_center:
        st.markdown("**Injection et timing**")

        injection_modes = ["Portal", "Artériel", "Intermédiaire"]
        injection_mode = st.radio(
            "Mode d'injection",
            injection_modes,
            horizontal=True,
            index=2,
            key="injection_mode_patient",
            label_visibility="collapsed"
        )

        if injection_mode == "Portal":
            base_time = float(cfg.get("portal_time", 30.0))
        elif injection_mode == "Artériel":
            base_time = float(cfg.get("arterial_time", 25.0))
        else:
            base_time = float(cfg.get("intermediate_time", cfg.get("portal_time", 30.0)))

        acquisition_start = calculate_acquisition_start(age, cfg)

        st.markdown(
            f"<div style='text-align:center; margin-top:6px;'>"
            f"<b>Temps {injection_mode.lower()} :</b> {base_time:.0f} s<br>"
            f"<b>Départ d'acquisition :</b> {acquisition_start:.1f} s"
            f"</div>",
            unsafe_allow_html=True
        )

    with col_div2:
        st.markdown("<div class='divider'></div>", unsafe_allow_html=True)

    # ⚙️ Bloc droit : options automatiques et simultanées
    with col_right:
        st.markdown("**Options avancées**")

        auto_age = bool(cfg.get("auto_acquisition_by_age", True))
        sim_enabled = bool(cfg.get("simultaneous_enabled", False))

        st.markdown(
            f"<div style='text-align:center;'>"
            f"<b>Ajustement automatique selon l'âge :</b><br>"
            f"{'✅ activé' if auto_age else '❌ désactivé'}<br><br>"
            f"<b>Injection simultanée :</b><br>"
            f"{'✅ activée' if sim_enabled else '❌ désactivée'}"
            f"</div>",
            unsafe_allow_html=True
        )
    st.markdown("</div>", unsafe_allow_html=True)

    # === LIGNE 2 : Poids / Taille / Année / Programme ===
    st.markdown("<div class='slider-red'>", unsafe_allow_html=True)
    current_year = datetime.now().year
    col_poids, col_taille, col_annee, col_prog = st.columns([1, 1, 1, 1.3])

    with col_poids:
        weight = st.slider("Poids (kg)", 20, 200, 70)

    with col_taille:
        height = st.slider("Taille (cm)", 100, 220, 170)

    with col_annee:
        min_year = current_year - 120
        max_year = current_year - 18
        default_birth = 1985 if 1985 <= max_year else max_year
        birth_year = st.slider("Année de naissance", min_year, max_year, default_birth)

    with col_prog:
        user_id = st.session_state["user_id"]
        user_programs = user_sessions.get(user_id, {}).get("programs", {})
        prog_choice_patient = st.selectbox(
            "Sélection d'un programme",
            ["Sélection d'un programme"] + list(user_programs.keys()),
            index=0
        )
        if prog_choice_patient != "Sélection d'un programme":
            prog_conf = user_programs.get(prog_choice_patient, {})
            cfg = get_cfg()
            for key, val in prog_conf.items():
                cfg[key] = val
            set_cfg_and_persist(user_id, cfg)
            user_sessions[user_id]["last_selected_program"] = prog_choice_patient
            save_user_sessions(user_sessions)
    st.markdown("</div>", unsafe_allow_html=True)

    # === Calculs et affichage des résultats (inchangé) ===
    cfg = get_cfg()
    age = current_year - birth_year
    imc = weight / ((height / 100) ** 2)

    volume_theorique, bsa = calculate_volume(
        weight, height, kv_scanner, float(cfg.get("concentration_mg_ml", 350)),
        imc, cfg.get("calc_mode", "Charge iodée"), cfg.get("charges", {}),
        float(cfg.get("volume_max_limit", 200.0))
    )

    if abs(volume_theorique - float(cfg.get("volume_max_limit", 200.0))) < 1e-6:
        st.warning("🧪 Volume plafonné par la capacité de la seringue.")

    if cfg.get("simultaneous_enabled", False):
        target = float(cfg.get("target_concentration", 350))
        current_conc = float(cfg.get("concentration_mg_ml", 350))
        if target > current_conc:
            target = current_conc
        vol_contrast_raw = volume_theorique * (target/current_conc) if current_conc > 0 else volume_theorique
        vol_nacl_dilution_raw = max(0.0, volume_theorique - vol_contrast_raw)
    else:
        vol_contrast_raw = volume_theorique
        vol_nacl_dilution_raw = 0.0

    vol_contrast_display = float(int(round(vol_contrast_raw)))
    rincage_display = float(int(round(cfg.get("rincage_volume", 35.0))))
    if cfg.get("simultaneous_enabled", False):
        vol_nacl_total_display = float(int(round(vol_nacl_dilution_raw + cfg.get("rincage_volume", 35.0))))
    else:
        vol_nacl_total_display = rincage_display

    if 'base_time' not in locals():
        base_time = float(cfg.get("portal_time", 30.0))
    injection_rate, injection_time, time_adjusted = adjust_injection_rate(
        vol_contrast_display, float(base_time), float(cfg.get("max_debit", 6.0))
    )

    st.markdown("---")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"<h4>💧 Volume contraste conseillé</h4><h2>{int(vol_contrast_display)} mL</h2>", unsafe_allow_html=True)
    with col2:
        st.markdown(f"<h4>💧 Volume NaCl conseillé</h4><h2>{int(vol_nacl_total_display)} mL</h2>", unsafe_allow_html=True)
    with col3:
        st.markdown(f"<h4>🚀 Débit conseillé</h4><h2>{injection_rate:.1f} mL/s</h2>", unsafe_allow_html=True)

    if time_adjusted:
        st.warning(f"⚠️ Temps d’injection ajusté à {injection_time:.1f}s pour respecter le débit maximal de {float(cfg.get('max_debit',6.0)):.1f} mL/s.")

    st.info(f"📏 IMC : {imc:.1f}" + (f" | Surface corporelle : {bsa:.2f} m²" if bsa else ""))
