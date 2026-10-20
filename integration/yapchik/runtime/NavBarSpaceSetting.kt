package app.vela.yapchik

import android.app.Activity
import android.content.Context
import android.os.Build
import android.view.WindowInsets
import com.theonionsarewatching.yapchik.Yapchik
import kotlin.math.roundToInt

/** The [NavBarSpace] choice, kept in Vela's backed-up settings and applied to Yapchik's nav guard. */
object NavBarSpaceSetting {
    private const val FILE = "vela_settings"
    private const val KEY = "yapchik_nav_bar_space"
    private const val DEFAULT_NAVIGATION_BAR_DP = 48

    fun get(context: Context): NavBarSpace = NavBarSpace.fromString(
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE).getString(KEY, null))

    fun set(activity: Activity, value: NavBarSpace) {
        activity.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit().putString(KEY, value.name).apply()
        apply(activity)
    }

    /** Sets [Yapchik.navGuardDp] for the current choice; a no-op when it is already in effect. */
    fun apply(activity: Activity) {
        if (!Yapchik.isInstalled) return
        val resources = activity.resources
        val heightId = resources.getIdentifier("navigation_bar_height", "dimen", "android")
        val heightDp = if (heightId == 0) DEFAULT_NAVIGATION_BAR_DP
            else (resources.getDimensionPixelSize(heightId) / resources.displayMetrics.density).roundToInt()
        val guard = navGuardDp(get(activity), hasOnScreenNavigation(activity), heightDp)
        if (Yapchik.navGuardDp != guard) Yapchik.navGuardDp = guard
    }

    /**
     * Android 11 and later report the navigation bar's size even while the softkey bar hides it.
     * Earlier versions only declare whether a navigation bar exists; a keypad phone's ROM often
     * declares one it never draws, so a declared bar counts only on a touch-first phone.
     */
    private fun hasOnScreenNavigation(activity: Activity): Boolean {
        val insets = activity.window?.peekDecorView()?.rootWindowInsets
        if (insets != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.R)
            return insets.getInsetsIgnoringVisibility(WindowInsets.Type.navigationBars()).bottom > 0
        val resources = activity.resources
        val showId = resources.getIdentifier("config_showNavigationBar", "bool", "android")
        return showId != 0 && resources.getBoolean(showId) && !Yapchik.autoDetector(activity)
    }
}
