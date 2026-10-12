package app.vela.yapchik

import android.app.Activity
import android.util.Log
import android.view.KeyEvent
import android.view.Window
import com.theonionsarewatching.yapchik.Softkeys
import com.theonionsarewatching.yapchik.Yapchik

private const val KEY_DIAGNOSTICS = false

internal fun attachKeyDiagnostics(activity: Activity): () -> Unit {
    if (!KEY_DIAGNOSTICS) return {}
    Softkeys.of(activity)
    val window = activity.window
    val wrapped = window.callback
    val observer = object : Window.Callback by wrapped {
        override fun dispatchKeyEvent(event: KeyEvent): Boolean {
            val trace = !event.isPrintingKey
            if (trace) {
                val profile = Yapchik.keyProfile
                Log.i("VelaYapchikKeys", "code=${event.keyCode} action=${event.action} repeat=${event.repeatCount} " +
                    "canceled=${event.isCanceled} flags=${event.flags} profile=${profile.id} " +
                    "left=${profile.leftKeys} right=${profile.rightKeys} slot=${profile.slotFor(event.keyCode)} " +
                    "shown=${Softkeys.isShownIn(activity)}")
            }
            val handled = wrapped.dispatchKeyEvent(event)
            if (trace) Log.i("VelaYapchikKeys", "code=${event.keyCode} action=${event.action} handled=$handled")
            return handled
        }
    }
    window.callback = observer
    return { if (window.callback === observer) window.callback = wrapped }
}
