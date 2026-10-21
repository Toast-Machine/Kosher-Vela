package app.vela.yapchik

import java.text.BreakIterator
import java.util.Locale

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

internal fun menuContentScale(contentWidth: Int, availableWidth: Int): Float =
    if (contentWidth <= 0) 1f else (availableWidth.toFloat() / contentWidth).coerceIn(0f, 1f)

/** Splits [text] at its legal line breaks (spaces, and between CJK characters). A wrapped label
 *  must fit its widest segment on one line, so wrapping never cuts through a word. */
internal fun unbreakableSegments(text: String, locale: Locale = Locale.getDefault()): List<String> {
    val breaks = BreakIterator.getLineInstance(locale).apply { setText(text) }
    val segments = mutableListOf<String>()
    var start = breaks.first()
    var end = breaks.next()
    while (end != BreakIterator.DONE) {
        text.substring(start, end).trim().takeIf { it.isNotEmpty() }?.let(segments::add)
        start = end
        end = breaks.next()
    }
    return segments
}

/** The largest text scale in [minScale]..1 that [fits], by bisection. Larger text never needs
 *  fewer lines, so the fitting scales form one interval starting at [minScale]. */
internal fun largestFittingScale(minScale: Float = 0.05f, steps: Int = 12, fits: (Float) -> Boolean): Float {
    if (fits(1f)) return 1f
    var low = minScale
    var high = 1f
    repeat(steps) {
        val middle = (low + high) / 2
        if (fits(middle)) low = middle else high = middle
    }
    return low
}
