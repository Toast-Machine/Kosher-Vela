package app.vela.yapchik

/** Whether the softkey bar grows to keep its labels above an on-screen navigation bar. */
enum class NavBarSpace {
    AUTO, OFF, ON;

    companion object {
        fun fromString(value: String?): NavBarSpace = entries.firstOrNull { it.name == value } ?: AUTO
    }
}

/**
 * The Yapchik nav-guard height (dp) for [choice]. null keeps Yapchik's own estimate of the
 * navigation bar height, 0 adds no space, and ON reserves the declared navigation bar height
 * even when the system currently reports no bar.
 */
internal fun navGuardDp(choice: NavBarSpace, onScreenNavigation: Boolean, navigationBarDp: Int): Int? = when (choice) {
    NavBarSpace.AUTO -> if (onScreenNavigation) null else 0
    NavBarSpace.OFF -> 0
    NavBarSpace.ON -> navigationBarDp
}
