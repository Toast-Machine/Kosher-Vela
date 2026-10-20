package app.vela.ui.settings

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.view.KeyEvent
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import app.vela.R
import app.vela.yapchik.NavBarSpace
import app.vela.yapchik.NavBarSpaceSetting
import com.theonionsarewatching.yapchik.KeyProfile
import com.theonionsarewatching.yapchik.SoftkeyMode
import com.theonionsarewatching.yapchik.SoftkeyProfileChooser
import com.theonionsarewatching.yapchik.Yapchik

/** Material Symbols Rounded "dialpad" (Apache License 2.0), built like the upstream `Sym` icons. */
internal val YapchikDialpad: ImageVector by lazy {
    ImageVector.Builder(name = "Yapchik.Dialpad", defaultWidth = 24.dp, defaultHeight = 24.dp,
        viewportWidth = 960f, viewportHeight = 960f)
        .addGroup(translationY = 960f)
        .addPath(pathData = addPathNodes("M480-40q-33 0-56.5-23.5T400-120q0-33 23.5-56.5T480-200q33 0 56.5 23.5T560-120q0 33-23.5 56.5T480-40ZM240-760q-33 0-56.5-23.5T160-840q0-33 23.5-56.5T240-920q33 0 56.5 23.5T320-840q0 33-23.5 56.5T240-760Zm0 240q-33 0-56.5-23.5T160-600q0-33 23.5-56.5T240-680q33 0 56.5 23.5T320-600q0 33-23.5 56.5T240-520Zm0 240q-33 0-56.5-23.5T160-360q0-33 23.5-56.5T240-440q33 0 56.5 23.5T320-360q0 33-23.5 56.5T240-280Zm480-480q-33 0-56.5-23.5T640-840q0-33 23.5-56.5T720-920q33 0 56.5 23.5T800-840q0 33-23.5 56.5T720-760ZM480-280q-33 0-56.5-23.5T400-360q0-33 23.5-56.5T480-440q33 0 56.5 23.5T560-360q0 33-23.5 56.5T480-280Zm240 0q-33 0-56.5-23.5T640-360q0-33 23.5-56.5T720-440q33 0 56.5 23.5T800-360q0 33-23.5 56.5T720-280Zm0-240q-33 0-56.5-23.5T640-600q0-33 23.5-56.5T720-680q33 0 56.5 23.5T800-600q0 33-23.5 56.5T720-520Zm-240 0q-33 0-56.5-23.5T400-600q0-33 23.5-56.5T480-680q33 0 56.5 23.5T560-600q0 33-23.5 56.5T480-520Zm0-240q-33 0-56.5-23.5T400-840q0-33 23.5-56.5T480-920q33 0 56.5 23.5T560-840q0 33-23.5 56.5T480-760Z"), fill = SolidColor(Color.Black))
        .clearGroup()
        .build()
}

private tailrec fun Context.settingsActivity(): Activity = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.settingsActivity()
    else -> error("Yapchik settings requires an Activity")
}

@Composable
private fun profileLabel(profile: KeyProfile): String = when (profile.id) {
    KeyProfile.UNIVERSAL_ID -> stringResource(R.string.yapchik_profile_universal)
    KeyProfile.STANDARD.id -> stringResource(R.string.yapchik_profile_standard)
    KeyProfile.MENU_BACK.id -> stringResource(R.string.yapchik_profile_menu_back)
    KeyProfile.FUNCTION.id -> stringResource(R.string.yapchik_profile_function)
    else -> profile.displayName
}

private fun keyNames(keys: Set<Int>): String =
    keys.joinToString(", ") { KeyEvent.keyCodeToString(it).removePrefix("KEYCODE_") }

@Composable
internal fun YapchikSettingsScreen(onBack: () -> Unit) {
    val activity = LocalContext.current.settingsActivity()
    var mode by remember { mutableStateOf(Yapchik.mode) }
    var profile by remember { mutableStateOf(Yapchik.keyProfile) }
    var navSpace by remember { mutableStateOf(NavBarSpaceSetting.get(activity)) }
    SettingsScaffold(stringResource(R.string.yapchik_settings_title), onBack) { topRow ->
        Spacer(Modifier.height(4.dp))
        PageIntro(stringResource(R.string.yapchik_settings_intro))
        Spacer(Modifier.height(8.dp))
        SettingsGroup(stringResource(R.string.yapchik_softkey_bar)) {
            for ((index, choice) in SoftkeyMode.entries.withIndex()) {
                val label = when (choice) {
                    SoftkeyMode.ON -> stringResource(R.string.yapchik_mode_on)
                    SoftkeyMode.OFF -> stringResource(R.string.yapchik_mode_off)
                    SoftkeyMode.AUTO -> stringResource(R.string.yapchik_mode_auto)
                }
                if (index > 0) GroupDivider()
                SelectableRow(label, mode == choice, {
                    Yapchik.mode = choice
                    mode = Yapchik.mode
                }, if (index == 0) topRow else Modifier)
            }
        }
        Spacer(Modifier.height(8.dp))
        SettingsGroup(stringResource(R.string.yapchik_nav_space)) {
            for ((index, choice) in listOf(NavBarSpace.AUTO, NavBarSpace.OFF, NavBarSpace.ON).withIndex()) {
                val label = when (choice) {
                    NavBarSpace.AUTO -> stringResource(R.string.yapchik_nav_space_auto)
                    NavBarSpace.OFF -> stringResource(R.string.yapchik_mode_off)
                    NavBarSpace.ON -> stringResource(R.string.yapchik_mode_on)
                }
                if (index > 0) GroupDivider()
                SelectableRow(label, navSpace == choice, {
                    NavBarSpaceSetting.set(activity, choice)
                    navSpace = NavBarSpaceSetting.get(activity)
                })
            }
        }
        Hint(stringResource(R.string.yapchik_nav_space_hint))
        Spacer(Modifier.height(8.dp))
        SettingsGroup(stringResource(R.string.yapchik_key_layout)) {
            for (choice in KeyProfile.BUILT_IN) {
                SelectableRow(profileLabel(choice), profile.id == choice.id, {
                    Yapchik.keyProfile = choice
                    profile = Yapchik.keyProfile
                })
                GroupDivider()
            }
            SelectableRow(stringResource(R.string.yapchik_profile_custom), profile.id == KeyProfile.CUSTOM_ID, {
                SoftkeyProfileChooser.startCalibration(activity) { profile = it }
            })
        }
        Hint(stringResource(R.string.yapchik_keys_hint, keyNames(profile.leftKeys), keyNames(profile.rightKeys)))
        Spacer(Modifier.height(24.dp))
    }
}
