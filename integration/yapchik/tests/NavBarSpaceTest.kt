package app.vela.yapchik

import org.junit.Assert.*
import org.junit.Test

class NavBarSpaceTest {
    @Test fun automaticIsTheDefaultForMissingOrUnknownValues() {
        assertEquals(NavBarSpace.AUTO, NavBarSpace.fromString(null))
        assertEquals(NavBarSpace.AUTO, NavBarSpace.fromString("sometimes"))
        for (choice in NavBarSpace.entries) assertEquals(choice, NavBarSpace.fromString(choice.name))
    }

    @Test fun automaticKeepsYapchikEstimateOnlyWithOnScreenNavigation() {
        assertNull(navGuardDp(NavBarSpace.AUTO, onScreenNavigation = true, navigationBarDp = 48))
        assertEquals(0, navGuardDp(NavBarSpace.AUTO, onScreenNavigation = false, navigationBarDp = 48))
    }

    @Test fun offAndOnIgnoreDetection() {
        for (detected in listOf(true, false)) {
            assertEquals(0, navGuardDp(NavBarSpace.OFF, detected, 48))
            assertEquals(42, navGuardDp(NavBarSpace.ON, detected, 42))
        }
    }
}
