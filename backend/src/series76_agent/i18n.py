"""Bilingual (ES/EN) response vocabulary for the deterministic composer.

Every template is static, digit-free text with ``{slot}`` placeholders; the
composer fills slots only with typed segments (see :mod:`series76_agent.rendering`).
The vocabulary contains no tool names, prompt text, or internal parameter
names (Req 5.2, 10.6). Part numbers and units are never translated.
"""

from __future__ import annotations

from series76_agent.domain.enums import Intent, Language, PresentationIntent
from series76_domain.model.enums import DataStatus, RequirementGroup
from series76_domain.model.filter_ast import AllowlistField, Operator

EN = Language.EN
ES = Language.ES

INTENT_LABELS: dict[Intent, dict[Language, str]] = {
    Intent.EXACT_LOOKUP: {EN: "Exact part lookup", ES: "Consulta exacta de una parte"},
    Intent.FILTER_SEARCH: {EN: "Filtered search", ES: "Búsqueda filtrada"},
    Intent.COMPARISON: {EN: "Comparison of parts", ES: "Comparación de partes"},
    Intent.RECOMMENDATION: {EN: "Recommendation", ES: "Recomendación"},
    Intent.DERIVED_CALCULATION: {EN: "Unit conversion", ES: "Conversión de unidades"},
    Intent.EXPLANATION: {
        EN: "Explanation from the source notes",
        ES: "Explicación a partir de las notas de la fuente",
    },
    Intent.FOLLOWUP: {
        EN: "Follow-up that needs clarification",
        ES: "Seguimiento que requiere aclaración",
    },
    Intent.OUT_OF_SCOPE: {
        EN: "Outside the provided document",
        ES: "Fuera del documento proporcionado",
    },
}

PRESENTATION_LABELS: dict[PresentationIntent, dict[Language, str]] = {
    PresentationIntent.SIMPLE: {
        EN: "Short answer with product card",
        ES: "Respuesta breve con ficha de producto",
    },
    PresentationIntent.LIST: {
        EN: "List of matching part numbers",
        ES: "Lista de números de parte coincidentes",
    },
    PresentationIntent.TOP_ONE: {
        EN: "Single recommendation with the count of eligible candidates",
        ES: "Una sola recomendación con el número de candidatos elegibles",
    },
    PresentationIntent.TABLE: {EN: "Comparison table", ES: "Tabla comparativa"},
    PresentationIntent.DUAL_COMPARISON: {
        EN: "Side-by-side comparison",
        ES: "Comparación lado a lado",
    },
    PresentationIntent.BAR_CHART: {
        EN: "Comparison table with comparable bar chart",
        ES: "Tabla comparativa con gráfico de barras comparable",
    },
}

FIELD_LABELS: dict[str, dict[Language, str]] = {
    AllowlistField.EXACT_PN.value: {EN: "part number", ES: "número de parte"},
    AllowlistField.ENCLOSURE.value: {EN: "enclosure", ES: "envolvente"},
    AllowlistField.NOMINAL_VOLTAGE.value: {EN: "nominal voltage", ES: "tensión nominal"},
    AllowlistField.CURRENT_MODE.value: {EN: "current mode", ES: "modo de corriente"},
    AllowlistField.PHASE.value: {EN: "phase", ES: "fase"},
    AllowlistField.SERVICE.value: {EN: "service type", ES: "tipo de servicio"},
    AllowlistField.TORQUE_INLBS.value: {EN: "torque (in-lbs)", ES: "par (in-lbs)"},
    AllowlistField.TORQUE_NM.value: {EN: "torque (Nm)", ES: "par (Nm)"},
    AllowlistField.DUTY_S4.value: {EN: "duty cycle (S4)", ES: "ciclo de trabajo (S4)"},
    AllowlistField.CYCLES_PER_HOUR.value: {EN: "cycles per hour", ES: "ciclos por hora"},
    AllowlistField.STARTS_PER_HOUR.value: {EN: "starts per hour", ES: "arranques por hora"},
    AllowlistField.OPERATING_SPEED.value: {
        EN: "operating speed",
        ES: "velocidad de operación",
    },
    AllowlistField.FLA.value: {
        EN: "full-load current (FLA)",
        ES: "corriente a plena carga (FLA)",
    },
    AllowlistField.LRA.value: {
        EN: "locked-rotor current (LRA)",
        ES: "corriente de rotor bloqueado (LRA)",
    },
    AllowlistField.MOTOR_POWER.value: {EN: "motor power", ES: "potencia del motor"},
    AllowlistField.NOTE.value: {EN: "source note", ES: "nota de la fuente"},
    AllowlistField.CERTIFICATION.value: {EN: "certification", ES: "certificación"},
}

OPERATOR_LABELS: dict[Operator, dict[Language, str]] = {
    Operator.EQ: {EN: "=", ES: "="},
    Operator.NE: {EN: "≠", ES: "≠"},
    Operator.LT: {EN: "<", ES: "<"},
    Operator.LE: {EN: "≤", ES: "≤"},
    Operator.GT: {EN: ">", ES: ">"},
    Operator.GE: {EN: "≥", ES: "≥"},
    Operator.IN: {EN: "one of", ES: "uno de"},
}

GROUP_LABELS: dict[RequirementGroup, dict[Language, str]] = {
    RequirementGroup.ENVIRONMENT_ENCLOSURE: {
        EN: "environment/enclosure",
        ES: "entorno/envolvente",
    },
    RequirementGroup.POWER_SUPPLY: {EN: "power supply", ES: "alimentación"},
    RequirementGroup.SERVICE_TYPE: {EN: "service type", ES: "tipo de servicio"},
    RequirementGroup.REQUIRED_TORQUE: {EN: "required torque", ES: "par requerido"},
}

STATUS_LABELS: dict[DataStatus, dict[Language, str]] = {
    DataStatus.NOT_APPLICABLE: {
        EN: "N/A (not applicable per the source)",
        ES: "N/A (no aplica según la fuente)",
    },
    DataStatus.NOT_DOCUMENTED: {EN: "not documented", ES: "no documentado"},
    DataStatus.NOT_LISTED: {EN: "not listed", ES: "no listado"},
    DataStatus.UNVERIFIED: {
        EN: "unverified (pending audit)",
        ES: "sin verificar (pendiente de auditoría)",
    },
}

BUDGET_LIMIT_LABELS: dict[str, dict[Language, str]] = {
    "max_model_calls_per_turn": {EN: "model-call limit", ES: "límite de llamadas al modelo"},
    "max_tool_calls_per_turn": {
        EN: "catalog-query limit",
        ES: "límite de consultas al catálogo",
    },
    "max_token_budget": {EN: "text-size limit", ES: "límite de tamaño de texto"},
    "max_walltime": {EN: "time limit", ES: "límite de tiempo"},
    "max_cost_usd": {EN: "cost limit", ES: "límite de coste"},
    "max_result_rows": {EN: "result-size limit", ES: "límite de tamaño de resultados"},
}

CONTEXT_WORDS: dict[str, dict[Language, str]] = {
    "service": {EN: "service", ES: "servicio"},
    "no_service": {EN: "no service attribution", ES: "sin atribución de servicio"},
    "supply": {EN: "supply", ES: "alimentación"},
    "derived": {EN: "derived, not an official value", ES: "derivado, no es un valor oficial"},
    "decimals": {EN: "decimal places", ES: "decimales"},
    "vs": {EN: "vs", ES: "frente a"},
    "your_requirement": {EN: "your stated requirement", ES: "requisito declarado por usted"},
    "and": {EN: "and", ES: "y"},
    "or": {EN: "or", ES: "o"},
    "not": {EN: "not", ES: "no"},
}

MESSAGES: dict[str, dict[Language, str]] = {
    "lookup_intro": {
        EN: "Documented data for {pn} ({edition}): ",
        ES: "Datos documentados de {pn} ({edition}): ",
    },
    "multi_measure": {
        EN: " Several documented measurements apply; each is shown with its service and "
        "frequency.",
        ES: " Aplican varias mediciones documentadas; cada una se muestra con su servicio y "
        "frecuencia.",
    },
    "part_na": {
        EN: " The source lists this part, but some attributes are not available: {items}.",
        ES: " La fuente lista esta parte, pero algunos atributos no están disponibles: {items}.",
    },
    "not_listed": {
        EN: "{pn} is not listed in {edition}. This only means it does not appear in the "
        "document; no similar part number is substituted.",
        ES: "{pn} no figura en {edition}. Esto solo significa que no aparece en el documento; "
        "no se sustituye por un número de parte similar.",
    },
    "invalid_pn": {
        EN: "{pn} does not have a valid part-number format. Please check it and send the "
        "corrected part number.",
        ES: "{pn} no tiene un formato válido de número de parte. Revíselo y envíe el número "
        "corregido.",
    },
    "search_results": {
        EN: "{count} part numbers in {edition} match the applied constraints ({constraints}).",
        ES: "{count} números de parte de {edition} cumplen las restricciones aplicadas "
        "({constraints}).",
    },
    "search_split": {
        EN: " {verified} satisfy every constraint with documented values; {preliminary} are "
        "indeterminate because a referenced value is N/A or not documented.",
        ES: " {verified} cumplen todas las restricciones con valores documentados; "
        "{preliminary} son indeterminados porque un valor referenciado es N/A o no está "
        "documentado.",
    },
    "search_page": {
        EN: " This is one page of the results; more are available.",
        ES: " Esta es una página de los resultados; hay más disponibles.",
    },
    "no_results": {
        EN: "No part number in {edition} matches the applied constraints ({constraints}). "
        "You can adjust them and try again.",
        ES: "Ningún número de parte de {edition} cumple las restricciones aplicadas "
        "({constraints}). Puede ajustarlas e intentarlo de nuevo.",
    },
    "comparison_intro": {
        EN: "Comparison of {pns} ({edition}). ",
        ES: "Comparación de {pns} ({edition}). ",
    },
    "comparison_not_comparable": {
        EN: " Not comparable (different operating context); no winner is declared.",
        ES: " No comparable (contexto de operación distinto); no se declara ganador.",
    },
    "fla_heterogeneous": {
        EN: " The current values come from different supply conditions; this does not "
        "indicate lower energy consumption or efficiency.",
        ES: " Los valores de corriente provienen de condiciones de alimentación distintas; "
        "esto no indica menor consumo de energía ni mayor eficiencia.",
    },
    "claim_has_more_torque": {
        EN: " {subject} documents more torque than {object} under the same conditions.",
        ES: " {subject} documenta más par que {object} en las mismas condiciones.",
    },
    "claim_is_faster": {
        EN: " {subject} documents a faster operating speed than {object} under the same "
        "conditions.",
        ES: " {subject} documenta una velocidad de operación más rápida que {object} en las "
        "mismas condiciones.",
    },
    "claim_same_frequency": {
        EN: " {subject} and {object} are documented at the same frequencies.",
        ES: " {subject} y {object} están documentados a las mismas frecuencias.",
    },
    "rec_verified": {
        EN: "Verified recommendation: environment, supply, service and torque are all "
        "specified and backed by documented matches in {edition}.",
        ES: "Recomendación verificada: entorno, alimentación, servicio y par están "
        "especificados y respaldados por coincidencias documentadas en {edition}.",
    },
    "rec_preliminary": {
        EN: "Preliminary results (not verified): these requirement groups are not fully "
        "specified: {groups}. These results do not assert final compatibility.",
        ES: "Resultados preliminares (no verificados): estos grupos de requisitos no están "
        "completamente especificados: {groups}. Estos resultados no afirman compatibilidad "
        "final.",
    },
    "rec_delegated": {
        EN: " You delegated {groups}; that is treated as a proposed preference, not as a "
        "documented physical condition.",
        ES: " Usted delegó {groups}; se trata como una preferencia propuesta, no como una "
        "condición física documentada.",
    },
    "rec_questions": {
        EN: " To verify the recommendation, please specify: {groups}.",
        ES: " Para verificar la recomendación, especifique: {groups}.",
    },
    "top_one": {
        EN: " Recommended part: {pn}, first by your accepted priority among {count} eligible "
        "candidates.",
        ES: " Parte recomendada: {pn}, la primera según su prioridad aceptada entre {count} "
        "candidatos elegibles.",
    },
    "top_one_none": {
        EN: " No candidate is eligible for the stated requirements; no winner is declared.",
        ES: " Ningún candidato es elegible para los requisitos indicados; no se declara "
        "ganador.",
    },
    "ranked": {
        EN: " Order by your accepted priority: {pns}.",
        ES: " Orden según su prioridad aceptada: {pns}.",
    },
    "rank_not_comparable": {
        EN: " The priority {metric} is not comparable across these candidates (different "
        "service, frequency, supply or unit), so no winner is declared. Indeterminate "
        "candidates: {pns}. Please choose another priority.",
        ES: " La prioridad {metric} no es comparable entre estos candidatos (servicio, "
        "frecuencia, alimentación o unidad distintos), así que no se declara ganador. "
        "Candidatos indeterminados: {pns}. Elija otra prioridad.",
    },
    "rank_limit": {
        EN: " There are too many candidates to rank within this request's limits; the full "
        "list of matches is shown instead. Please narrow the criteria.",
        ES: " Hay demasiados candidatos para ordenar dentro de los límites de esta "
        "solicitud; se muestra la lista completa de coincidencias. Acote los criterios.",
    },
    "derived": {
        EN: "Conversion for {pn} ({edition}): {source} corresponds to {derived}.",
        ES: "Conversión para {pn} ({edition}): {source} corresponde a {derived}.",
    },
    "derived_unavailable": {
        EN: "The value to convert for {pn} is not available in {edition}: {items}. No "
        "converted value is produced.",
        ES: "El valor a convertir de {pn} no está disponible en {edition}: {items}. No se "
        "produce un valor convertido.",
    },
    "notes_intro": {
        EN: "Source notes for {pn} ({edition}): ",
        ES: "Notas de la fuente para {pn} ({edition}): ",
    },
    "notes_none": {
        EN: "No source note is documented for {pn} in {edition}.",
        ES: "No hay notas documentadas para {pn} en {edition}.",
    },
    "scope_without_evidence": {
        EN: " The document has no data for the requested {item} of {pn}; only the documented "
        "scope is shown.",
        ES: " El documento no tiene datos para el {item} solicitado de {pn}; solo se muestra "
        "el alcance documentado.",
    },
    "abstain": {
        EN: "That information is not in the source I can use ({edition}). I only answer from "
        "that document, so I will not add outside facts.",
        ES: "Esa información no está en la fuente que puedo usar ({edition}). Solo respondo "
        "a partir de ese documento, así que no añadiré hechos externos.",
    },
    "clarify_invalid_filter": {
        EN: "I could not apply the condition on {field}: the operator or unit does not "
        "apply to that field. Could you rephrase it?",
        ES: "No pude aplicar la condición sobre {field}: el operador o la unidad no aplican "
        "a ese campo. ¿Podría reformularla?",
    },
    "clarify_invalid_filter_generic": {
        EN: "I could not build a valid filter from that request. Could you rephrase the "
        "constraints?",
        ES: "No pude construir un filtro válido con esa solicitud. ¿Podría reformular las "
        "restricciones?",
    },
    "clarify_ambiguous": {
        EN: "Your request can be read in more than one way. Which one did you mean?",
        ES: "Su solicitud puede interpretarse de más de una forma. ¿Cuál quiso decir?",
    },
    "clarify_conflict": {
        EN: "Some of your statements conflict with each other. Which one should apply?",
        ES: "Algunas de sus indicaciones se contradicen. ¿Cuál debe aplicarse?",
    },
    "clarify_ref_unmatched": {
        EN: "I cannot find {ref} in this conversation. Which part number do you mean?",
        ES: "No encuentro {ref} en esta conversación. ¿A qué número de parte se refiere?",
    },
    "clarify_ref_ambiguous": {
        EN: "{ref} could refer to {pns}. Which one do you mean?",
        ES: "{ref} podría referirse a {pns}. ¿A cuál se refiere?",
    },
    "clarify_priority": {
        EN: "To rank the candidates I need your priority. Which metric should decide, for "
        "example torque, operating speed or current?",
        ES: "Para ordenar los candidatos necesito su prioridad. ¿Qué métrica debe decidir, "
        "por ejemplo par, velocidad de operación o corriente?",
    },
    "clarify_missing_pn": {
        EN: "Which part number should I look up?",
        ES: "¿Qué número de parte debo consultar?",
    },
    "clarify_compare_arity": {
        EN: "Please name two or three part numbers to compare.",
        ES: "Indique dos o tres números de parte para comparar.",
    },
    "clarify_missing_filter": {
        EN: "Which constraints should I search with?",
        ES: "¿Con qué restricciones debo buscar?",
    },
    "clarify_target_unit": {
        EN: "Which part number and target unit should I use for the conversion?",
        ES: "¿Qué número de parte y unidad de destino debo usar para la conversión?",
    },
    "clarify_followup": {
        EN: "Could you clarify what you would like to know?",
        ES: "¿Podría aclarar qué desea saber?",
    },
    "confirm_plan": {
        EN: "Please review and confirm this plan (revision {rev}) before I run it.",
        ES: "Revise y confirme este plan (revisión {rev}) antes de ejecutarlo.",
    },
    "confirm_boolean": {
        EN: " Your conditions combine AND/OR in a way that could be grouped differently. "
        "I will apply them exactly as: {expr}.",
        ES: " Sus condiciones combinan Y/O de una forma que podría agruparse distinto. Las "
        "aplicaré exactamente así: {expr}.",
    },
    "confirm_priority": {
        EN: " I propose ranking by {priorities}; it is only applied if you confirm it.",
        ES: " Propongo ordenar por {priorities}; solo se aplica si usted lo confirma.",
    },
    "confirm_delegation": {
        EN: " Your delegation would change which results are returned, so it needs your "
        "confirmation.",
        ES: " Su delegación cambiaría los resultados devueltos, por lo que requiere su "
        "confirmación.",
    },
    "stale": {
        EN: "The plan changed since you reviewed it. The current plan is revision {rev}; the "
        "older revision was not executed.",
        ES: "El plan cambió desde que lo revisó. El plan vigente es la revisión {rev}; la "
        "revisión anterior no se ejecutó.",
    },
    "already_executed": {
        EN: "This plan revision was already executed; it was not run again.",
        ES: "Esta revisión del plan ya se ejecutó; no se volvió a ejecutar.",
    },
    "withdrawn": {
        EN: "The pinned source edition ({edition}) has been withdrawn, so no new "
        "recommendation can be made from it. Your conversation history is kept.",
        ES: "La edición de la fuente fijada ({edition}) fue retirada, así que no se pueden "
        "hacer nuevas recomendaciones con ella. Su historial se conserva.",
    },
    "cancelled": {
        EN: "This request was cancelled; no result was produced.",
        ES: "Esta solicitud fue cancelada; no se produjo ningún resultado.",
    },
    "budget": {
        EN: "I stopped this request because it reached the {limit}. No partial result is "
        "presented as complete. Please narrow the request.",
        ES: "Detuve esta solicitud porque alcanzó el {limit}. Ningún resultado parcial se "
        "presenta como completo. Acote la solicitud.",
    },
    "tool_unavailable": {
        EN: "The catalog is temporarily unavailable. Please try again. Reference: {ref}.",
        ES: "El catálogo no está disponible temporalmente. Inténtelo de nuevo. "
        "Referencia: {ref}.",
    },
    "provider_quota": {
        EN: "The language service quota is exhausted, so this request cannot be processed "
        "now. No answer was invented.",
        ES: "La cuota del servicio de lenguaje está agotada, así que no se puede procesar "
        "la solicitud ahora. No se inventó ninguna respuesta.",
    },
    "provider_unavailable": {
        EN: "The language service is temporarily unavailable. Please try again.",
        ES: "El servicio de lenguaje no está disponible temporalmente. Inténtelo de nuevo.",
    },
    "unsupported_capability": {
        EN: "The configured language model endpoint does not support a required capability, "
        "so the request was not sent.",
        ES: "El endpoint del modelo configurado no admite una capacidad requerida, así que "
        "la solicitud no se envió.",
    },
    "cost_cap": {
        EN: "The usage budget for this environment has been reached, so the request was not "
        "sent.",
        ES: "Se alcanzó el presupuesto de uso de este entorno, así que la solicitud no se "
        "envió.",
    },
    "edition_unavailable": {
        EN: "No published catalog edition is available for this conversation, so I cannot "
        "answer from the source.",
        ES: "No hay una edición publicada del catálogo para esta conversación, así que no "
        "puedo responder a partir de la fuente.",
    },
    "insufficient_information": {
        EN: " There is not enough documented information to state that reliably.",
        ES: " No hay información documentada suficiente para afirmarlo con fiabilidad.",
    },
    "injection_note": {
        EN: " Instructions in the message that conflict with the assistant's rules were "
        "ignored.",
        ES: " Se ignoraron instrucciones del mensaje que contradicen las reglas del " "asistente.",
    },
    "withheld": {
        EN: " Some values were withheld because their source reference could not be " "resolved.",
        ES: " Algunos valores se omitieron porque su referencia a la fuente no pudo " "resolverse.",
    },
}


def msg(key: str, lang: Language) -> str:
    """Return the template for ``key`` in ``lang``."""
    return MESSAGES[key][lang]


def label(table: dict[str, dict[Language, str]], key: str, lang: Language) -> str:
    """Localized label for ``key`` (falls back to a neutral word, never the raw key)."""
    entry = table.get(key)
    if entry is None:
        return "value" if lang is Language.EN else "valor"
    return entry[lang]


def metric_label(metric_key: str, lang: Language) -> str:
    """Localized display label of a metric key (derived keys keep the base label)."""
    base = metric_key.split("->", 1)[0]
    return label(FIELD_LABELS, base, lang)
