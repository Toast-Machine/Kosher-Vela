package app.vela.yapchik

sealed interface ActionVisual {
    data class Label(val text: String) : ActionVisual
    data class Glyph(val value: Any, val description: String?) : ActionVisual
    data class Toggle(val kind: String) : ActionVisual
}

internal fun menuPresentation(presentation: List<ActionVisual>): List<ActionVisual> {
    if (presentation.any { it is ActionVisual.Label && it.text.isNotBlank() }) return presentation
    val descriptions = mutableSetOf<String>()
    return buildList {
        for (visual in presentation) {
            val description = (visual as? ActionVisual.Glyph)?.description?.takeIf { it.isNotBlank() }
            if (visual is ActionVisual.Glyph && description != null) {
                add(visual.copy(description = null))
                if (descriptions.add(description)) add(ActionVisual.Label(description))
            } else add(visual)
        }
    }
}
