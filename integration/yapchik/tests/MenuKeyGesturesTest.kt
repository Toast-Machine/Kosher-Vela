package app.vela.yapchik

import org.junit.Assert.*
import org.junit.Test

class MenuKeyGesturesTest {
    @Test fun capturedGestureCannotLeakAfterMenuDismissal() {
        val gestures = MenuKeyGestures()
        assertTrue(gestures.consume(23, true, true))
        assertTrue(gestures.consume(23, true, false))
        assertTrue(gestures.consume(23, false, false))
        assertFalse(gestures.consume(23, true, false))
        assertFalse(gestures.consume(23, false, false))
    }

    @Test fun unrelatedKeysRemainIndependent() {
        val gestures = MenuKeyGestures()
        assertTrue(gestures.consume(23, true, true))
        assertFalse(gestures.consume(66, false, false))
        assertTrue(gestures.consume(23, false, false))
    }

    @Test fun menuOpenedMidGestureStillConsumesRelease() {
        val gestures = MenuKeyGestures()
        assertFalse(gestures.consume(23, true, false))
        assertTrue(gestures.consume(23, false, true))
    }
}
