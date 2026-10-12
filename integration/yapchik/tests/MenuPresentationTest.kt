package app.vela.yapchik

import org.junit.Assert.*
import org.junit.Test

class MenuPresentationTest {
    @Test fun iconDescriptionsBecomeVisibleAccessibleLabels() {
        val icon = Any()
        assertEquals(listOf(ActionVisual.Glyph(icon, null), ActionVisual.Label("Save parking")),
            menuPresentation(listOf(ActionVisual.Glyph(icon, "Save parking"))))
    }

    @Test fun existingTextAndIconDescriptionsRemainUnchanged() {
        val presentation = listOf(ActionVisual.Glyph(Any(), "Category"), ActionVisual.Label("Restaurants"))
        assertSame(presentation, menuPresentation(presentation))
    }

    @Test fun missingDescriptionsDoNotInventLabels() {
        val presentation = listOf(ActionVisual.Glyph(Any(), null), ActionVisual.Glyph(Any(), "   "), ActionVisual.Toggle("Switch"))
        assertEquals(presentation, menuPresentation(presentation))
        assertTrue(menuPresentation(emptyList()).isEmpty())
    }

    @Test fun duplicateDescriptionsAreNotAnnouncedTwice() {
        val presentation = listOf(ActionVisual.Glyph(Any(), "Settings"), ActionVisual.Glyph(Any(), "Settings"))
        val result = menuPresentation(presentation)
        assertEquals(listOf(ActionVisual.Label("Settings")), result.filterIsInstance<ActionVisual.Label>())
        assertTrue(result.filterIsInstance<ActionVisual.Glyph>().all { it.description == null })
    }

    @Test fun distinctDescriptionsAndLocalizedValuesAreRetained() {
        val presentation = listOf(ActionVisual.Glyph(Any(), "חניה"), ActionVisual.Glyph(Any(), "Details"))
        assertEquals(listOf("חניה", "Details"), menuPresentation(presentation).filterIsInstance<ActionVisual.Label>().map { it.text })
    }

    @Test fun descriptionsFollowCurrentPresentationValues() {
        val icon = Any()
        assertEquals(ActionVisual.Label("Save parking"), menuPresentation(listOf(ActionVisual.Glyph(icon, "Save parking"))).last())
        assertEquals(ActionVisual.Label("Parked car"), menuPresentation(listOf(ActionVisual.Glyph(icon, "Parked car"))).last())
    }
}
