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
    private var declaredDp: Int? = null

    fun get(context: Context): NavBarSpace = NavBarSpace.fromString(
        context.getSharedPreferences(FILE, Context.MODE_PRIVATE).getString(KEY, null))

    fun set(activity: Activity, value: NavBarSpace) {
        activity.getSharedPreferences(FILE, Context.MODE_PRIVATE).edit().putString(KEY, value.name).apply()
        apply(activity)
    }

    /**
     * Sets [Yapchik.navGuardDp] for the current choice and navigation bar; a no-op when it is
     * already in effect. Called on every layout of the window, so AUTO follows the navigation
     * bar as it is shown and hidden.
     */
    fun apply(activity: Activity) {
        if (!Yapchik.isInstalled) return
        val density = activity.resources.displayMetrics.density
        val showingDp = (showingNavigationBarPx(activity) / density).roundToInt()
        val guard = navGuardDp(get(activity), showingDp, declaredNavigationBarDp(activity))
        if (Yapchik.navGuardDp != guard) Yapchik.navGuardDp = guard
    }

    private fun declaredNavigationBarDp(activity: Activity): Int = declaredDp ?: run {
        val resources = activity.resources
        val heightId = resources.getIdentifier("navigation_bar_height", "dimen", "android")
        (if (heightId == 0) DEFAULT_NAVIGATION_BAR_DP
            else (resources.getDimensionPixelSize(heightId) / resources.displayMetrics.density).roundToInt())
            .also { declaredDp = it }
    }

    /**
     * The height of the navigation bar the system is showing at the bottom of the window right
     * now, or 0 while it is hidden; the softkey bar asks the system to hide it. Before Android 11,
     * the bottom system inset also covers an open keyboard, so it is capped at the stable
     * navigation bar height.
     */
    private fun showingNavigationBarPx(activity: Activity): Int {
        val insets = activity.window?.peekDecorView()?.rootWindowInsets ?: return 0
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val type = WindowInsets.Type.navigationBars()
            return if (insets.isVisible(type)) insets.getInsets(type).bottom else 0
        }
        @Suppress("DEPRECATION")
        return minOf(insets.systemWindowInsetBottom, insets.stableInsetBottom)
    }
}
