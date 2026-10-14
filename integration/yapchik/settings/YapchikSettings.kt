package app.vela.ui.settings

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import com.theonionsarewatching.yapchik.KeyProfile
import com.theonionsarewatching.yapchik.SoftkeyMode
import com.theonionsarewatching.yapchik.SoftkeyProfileChooser
import com.theonionsarewatching.yapchik.Yapchik

private tailrec fun Context.settingsActivity(): Activity = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.settingsActivity()
    else -> error("Yapchik settings requires an Activity")
}

@Composable
internal fun YapchikSettingsScreen(onBack: () -> Unit) {
    val activity = LocalContext.current.settingsActivity()
    var mode by remember { mutableStateOf(Yapchik.mode) }
    var profile by remember { mutableStateOf(Yapchik.keyProfile) }
    SettingsScaffold("Yapchik", onBack) { topRow ->
        PageIntro("Hardware softkeys and key calibration")
        SettingsGroup("Softkeys") {
            for ((index, choice) in SoftkeyMode.entries.withIndex()) {
                val label = when (choice) {
                    SoftkeyMode.ON -> "On"
                    SoftkeyMode.OFF -> "Off"
                    SoftkeyMode.AUTO -> "Automatic — detect keypad device"
                }
                SelectableRow(label, mode == choice, {
                    Yapchik.mode = choice
                    mode = Yapchik.mode
                }, if (index == 0) topRow else Modifier)
            }
        }
        SettingsGroup("Key layout") {
            for (choice in KeyProfile.BUILT_IN) {
                SelectableRow(choice.displayName, profile.id == choice.id, {
                    Yapchik.keyProfile = choice
                    profile = Yapchik.keyProfile
                })
            }
            SelectableRow("Custom — detect my keys", profile.id == KeyProfile.CUSTOM_ID, {
                SoftkeyProfileChooser.startCalibration(activity) { profile = it }
            })
        }
        Hint(profile.describe())
    }
}
