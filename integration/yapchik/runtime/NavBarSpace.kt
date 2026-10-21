package app.vela.yapchik

/** Whether the softkey bar grows to keep its labels above an on-screen navigation bar. */
enum class NavBarSpace {
    AUTO, OFF, ON;

    companion object {
        fun fromString(value: String?): NavBarSpace = entries.firstOrNull { it.name == value } ?: AUTO
    }
}

/**
 * The Yapchik nav-guard height (dp) for [choice]. AUTO matches the navigation bar the system is
 * showing right now (0 while it is hidden), OFF adds no space, and ON reserves the declared
 * navigation bar height even while the system reports the bar hidden.
 */
internal fun navGuardDp(choice: NavBarSpace, showingNavigationBarDp: Int, navigationBarDp: Int): Int = when (choice) {
    NavBarSpace.AUTO -> showingNavigationBarDp
    NavBarSpace.OFF -> 0
    NavBarSpace.ON -> navigationBarDp
}
