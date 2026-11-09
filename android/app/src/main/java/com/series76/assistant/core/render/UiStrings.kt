package com.series76.assistant.core.render

/**
 * Resolves [UiText] for display. [UiText.Raw] (backend data: part numbers,
 * values, units, contexts) is returned unchanged in every language; only
 * [UiText.Res] keys are localized (Spec 5 Req 10.1, 10.2; Property 32).
 */
interface UiStrings {
    fun string(key: String, args: List<String> = emptyList()): String

    fun resolve(text: UiText): String = when (text) {
        is UiText.Raw -> text.text
        is UiText.Res -> string(text.key, text.args.map { arg -> TABLE_EN[arg]?.let { string(arg) } ?: arg })
    }
}

/** A table-backed resolver (JVM tests; mirrors the keys of the res/values and res/values-es strings.xml files). */
class TableUiStrings(private val language: String) : UiStrings {
    override fun string(key: String, args: List<String>): String {
        val table = if (language == "es") TABLE_ES else TABLE_EN
        val template = table[key] ?: TABLE_EN[key] ?: key // default-language fallback
        return args.foldIndexed(template) { i, acc, arg -> acc.replace("{$i}", arg) }
    }
}

internal val TABLE_EN: Map<String, String> = mapOf(
    "state_not_applicable" to "N/A (not applicable)",
    "state_not_documented" to "Not documented",
    "state_not_listed" to "Not listed",
    "state_unverified" to "Unverified",
    "state_unavailable" to "Unavailable",
    "derived_note" to "Derived value, not official: {0}",
    "note_not_comparable" to "Not comparable (different context); no winner",
    "note_supply_heterogeneous" to "Different supply conditions; not an energy-efficiency comparison",
    "bar_alt_state" to "{0}: {1}",
    "offline_banner" to "You are offline. Saved conversations can be viewed, but messages cannot be sent until the connection returns.",
)

internal val TABLE_ES: Map<String, String> = mapOf(
    "state_not_applicable" to "N/A (no aplica)",
    "state_not_documented" to "No documentado",
    "state_not_listed" to "No listado",
    "state_unverified" to "Sin verificar",
    "state_unavailable" to "No disponible",
    "derived_note" to "Valor derivado, no oficial: {0}",
    "note_not_comparable" to "No comparable (contexto distinto); sin ganador",
    "note_supply_heterogeneous" to "Condiciones de alimentación distintas; no es una comparación de eficiencia energética",
    "bar_alt_state" to "{0}: {1}",
    "offline_banner" to "Sin conexión. Puede ver las conversaciones guardadas, pero no enviar mensajes hasta que vuelva la conexión.",
)
