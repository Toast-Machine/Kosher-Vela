package app.vela.yapchik

import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import android.content.res.Configuration
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
     * An on-screen navigation bar is a touch control. Without a touchscreen, what Android reports
     * as a navigation bar is the ROM's softkey label strip, which the softkey bar hides and
     * replaces. On a touch phone, Android 11 and later report the navigation bar's size even while
     * the softkey bar hides it; earlier versions only declare whether one exists.
     */
    private fun hasOnScreenNavigation(activity: Activity): Boolean {
        val touch = activity.packageManager.hasSystemFeature(PackageManager.FEATURE_TOUCHSCREEN) &&
            activity.resources.configuration.touchscreen != Configuration.TOUCHSCREEN_NOTOUCH
        if (!touch) return false
        val insets = activity.window?.peekDecorView()?.rootWindowInsets
        if (insets != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.R)
            return insets.getInsetsIgnoringVisibility(WindowInsets.Type.navigationBars()).bottom > 0
        val resources = activity.resources
        val showId = resources.getIdentifier("config_showNavigationBar", "bool", "android")
        return showId != 0 && resources.getBoolean(showId)
    }
}
