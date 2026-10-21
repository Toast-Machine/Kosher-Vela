package app.vela.yapchik

import org.junit.Assert.*
import org.junit.Test

class NavBarSpaceTest {
    @Test fun automaticIsTheDefaultForMissingOrUnknownValues() {
        assertEquals(NavBarSpace.AUTO, NavBarSpace.fromString(null))
        assertEquals(NavBarSpace.AUTO, NavBarSpace.fromString("sometimes"))
        for (choice in NavBarSpace.entries) assertEquals(choice, NavBarSpace.fromString(choice.name))
    }

    @Test fun automaticMatchesTheNavigationBarShowingNow() {
        assertEquals(19, navGuardDp(NavBarSpace.AUTO, showingNavigationBarDp = 19, navigationBarDp = 48))
        assertEquals(0, navGuardDp(NavBarSpace.AUTO, showingNavigationBarDp = 0, navigationBarDp = 48))
    }

    @Test fun offAndOnIgnoreWhetherTheBarIsShowing() {
        for (showing in listOf(0, 19)) {
            assertEquals(0, navGuardDp(NavBarSpace.OFF, showing, 48))
            assertEquals(42, navGuardDp(NavBarSpace.ON, showing, 42))
        }
    }
}
