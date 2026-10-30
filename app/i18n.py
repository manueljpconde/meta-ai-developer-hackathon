"""One place per language for every translated string.

`pt-PT` and `en-GB` hold the same keys. A missing key raises instead
of falling back, so a missing translation fails loudly. Fiscal terms
stay in Portuguese in English (foundation 14.4).
"""

STRINGS = {
    "pt-PT": {
        "nav_home": "Previsão",
        "nav_new": "Novo negócio",
        "nav_settings": "Definições",
        "lang_label": "Idioma",
        "lang_change": "Mudar",
        "home_title": "Previsão",
        "home_empty": "Ainda não tens negócios. Regista o primeiro para veres quanto vais receber.",
        "home_new": "Novo negócio",
        "m_commission": "Comissão",
        "m_bank": "Entrará na conta",
        "m_protected": "Dinheiro a proteger",
        "m_really": "É realmente teu",
        "m_share": "A tua parte",
        "m_expenses": "Despesas",
        "m_deals": "Negócios",
        "b_iva": "IVA",
        "b_irs": "IRS",
        "b_ss": "Segurança Social",
        "set_title": "Definições",
        "set_share": "A tua percentagem (%)",
        "set_iva": "IVA (%)",
        "set_retencao": "Retenção na fonte (%)",
        "set_irs": "Reserva IRS (%)",
        "set_ss": "Reserva Segurança Social, estimativa (%)",
        "set_expenses": "Despesas mensais (€)",
        "set_save": "Guardar",
        "deal_title": "Novo negócio",
        "f_name": "Nome do negócio",
        "f_commission": "Comissão da agência (sem IVA) (€)",
        "f_share": "A tua percentagem (%)",
        "f_month": "Quando esperas receber",
        "f_stage": "Fase",
        "st_potencial": "Potencial",
        "st_provavel": "Provável",
        "st_confirmado": "Confirmado",
        "f_agency": "Agência (opcional)",
        "btn_review": "Rever",
        "rev_title": "Rever negócio",
        "btn_confirm": "Confirmar",
        "stale_msg": "Os valores foram atualizados. Revê antes de confirmar.",
        "err_name": "Indica o nome do negócio.",
        "err_commission": "Indica a comissão da agência.",
        "err_percent": "Introduz uma percentagem entre 0 e 100.",
        "err_amount": "Introduz o valor sem separadores de milhares: 5000,50.",
        "err_positive": "O valor tem de ser maior do que zero.",
        "err_month": "Escolhe o mês esperado.",
        "err_stage": "Escolhe a fase.",
        "err_too_long": "O texto tem de ter no máximo 200 caracteres.",
        "err_settings": "Define primeiro as definições.",
        "move_title": "Cenário: mover pagamento",
        "nl_label": "Descreve a mudança",
        "nl_hint": "Por exemplo: Move the Benfica payment to January.",
        "nl_submit": "Simular",
        "nl_before": "Antes",
        "nl_after": "Depois",
        "refused_title": "Pedido recusado",
        "refused_msg": "Não foi possível validar o pedido. Nada foi alterado.",
    },
    "en-GB": {
        "nav_home": "Forecast",
        "nav_new": "New deal",
        "nav_settings": "Settings",
        "lang_label": "Language",
        "lang_change": "Change",
        "home_title": "Forecast",
        "home_empty": "You have no deals yet. Record the first one to see how much you will receive.",
        "home_new": "New deal",
        "m_commission": "Commission",
        "m_bank": "Will reach your account",
        "m_protected": "Money to set aside",
        "m_really": "Really yours",
        "m_share": "Your share",
        "m_expenses": "Expenses",
        "m_deals": "Deals",
        "b_iva": "IVA",
        "b_irs": "IRS",
        "b_ss": "Segurança Social",
        "set_title": "Settings",
        "set_share": "Your percentage (%)",
        "set_iva": "IVA (%)",
        "set_retencao": "Retenção na fonte (%)",
        "set_irs": "IRS reserve (%)",
        "set_ss": "Segurança Social reserve, estimate (%)",
        "set_expenses": "Monthly expenses (€)",
        "set_save": "Save",
        "deal_title": "New deal",
        "f_name": "Deal name",
        "f_commission": "Agency commission (excl. IVA) (€)",
        "f_share": "Your percentage (%)",
        "f_month": "When do you expect to receive it",
        "f_stage": "Stage",
        "st_potencial": "Potential",
        "st_provavel": "Likely",
        "st_confirmado": "Confirmed",
        "f_agency": "Agency (optional)",
        "btn_review": "Review",
        "rev_title": "Review deal",
        "btn_confirm": "Confirm",
        "stale_msg": "The figures were updated. Review before confirming.",
        "err_name": "Enter the deal name.",
        "err_commission": "Enter the agency commission.",
        "err_percent": "Enter a percentage between 0 and 100.",
        "err_amount": "Enter the amount without thousands separators: 5000.50.",
        "err_positive": "The amount must be greater than zero.",
        "err_month": "Choose the expected month.",
        "err_stage": "Choose the stage.",
        "err_too_long": "The text must be at most 200 characters.",
        "err_settings": "Set up your settings first.",
        "move_title": "Scenario: move payment",
        "nl_label": "Describe the move",
        "nl_hint": "For example: Move the Benfica payment to January.",
        "nl_submit": "Preview move",
        "nl_before": "Before",
        "nl_after": "After",
        "refused_title": "Request refused",
        "refused_msg": "The request could not be verified. Nothing was changed.",
    },
}

SUPPORTED = ("pt-PT", "en-GB")


def text(lang, key):
    """Return the string for a language, raising on a missing key."""
    return STRINGS[lang][key]


def detect_language(header):
    """Match Accept-Language by language family: en-* to en-GB,
    pt-* to pt-PT, anything else (or absent) to pt-PT."""
    if not header:
        return "pt-PT"
    for item in header.split(","):
        code = item.split(";")[0].strip().lower()
        family = code.split("-")[0]
        if family == "en":
            return "en-GB"
        if family == "pt":
            return "pt-PT"
    return "pt-PT"
