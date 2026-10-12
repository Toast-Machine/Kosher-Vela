package app.vela.yapchik

import org.junit.Assert.*
import org.junit.Test

class MenuPresentationTest {
    @Test fun wideOptionsScaleDownWithoutGrowingShortOptions() {
        assertEquals(0.5f, menuContentScale(400, 200), 0f)
        assertEquals(0.25f, menuContentScale(800, 200), 0f)
        assertEquals(1f, menuContentScale(100, 200), 0f)
        assertEquals(1f, menuContentScale(200, 200), 0f)
    }

    @Test fun emptyOrZeroWidthOptionsDoNotProduceInvalidScales() {
        assertEquals(1f, menuContentScale(0, 200), 0f)
        assertEquals(0f, menuContentScale(100, 0), 0f)
        assertEquals(0f, menuContentScale(100, -1), 0f)
    }

    @Test fun scaledContentFitsPortraitLandscapeAndVeryNarrowWidths() {
        for (available in listOf(1, 60, 120, 240, 427, 600)) {
            for (content in listOf(1, 50, 120, 400, 1800)) {
                val scale = menuContentScale(content, available)
                assertTrue(scale in 0f..1f)
                assertTrue(content * scale <= available + 0.001f)
            }
        }
    }

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
