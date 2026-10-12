package app.vela.yapchik

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.view.KeyEvent
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.layout.LayoutCoordinates
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.theonionsarewatching.yapchik.SoftkeyMode
import com.theonionsarewatching.yapchik.Softkeys
import com.theonionsarewatching.yapchik.Yapchik
import com.theonionsarewatching.yapchik.YapchikSettingsDialog

sealed interface ActionVisual {
    data class Label(val text: String) : ActionVisual
    data class Glyph(val value: Any, val description: String?) : ActionVisual
    data class Toggle(val kind: String) : ActionVisual
}

private val LocalStore = staticCompositionLocalOf<ActionStore<ActionVisual>?> { null }
private val LocalOwner = staticCompositionLocalOf<Any?> { null }
private val LocalItemKeys = staticCompositionLocalOf<List<Any>> { emptyList() }
@PublishedApi internal val LocalAction = staticCompositionLocalOf<ActionHandle?> { null }

private class ObjectIdentity(private val value: Any) {
    override fun equals(other: Any?): Boolean = other is ObjectIdentity && other.value === value
    override fun hashCode(): Int = System.identityHashCode(value)
}

private data class DataIdentity(val type: String, val value: Any)

private fun itemKey(value: Any?): Any {
    if (value == null) return DataIdentity("null", "null")
    if (value is String || value is Number || value is Enum<*>) return DataIdentity(value.javaClass.name, value)
    val identity = runCatching {
        value.javaClass.methods.singleOrNull { it.name == "getId" && it.parameterCount == 0 }?.invoke(value)
    }.getOrNull()
    return if (identity != null) DataIdentity(value.javaClass.name, identity) else ObjectIdentity(value)
}

@Composable
fun YapchikItem(source: String, value: Any?, content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalItemKeys provides (LocalItemKeys.current + DataIdentity("site", source) + itemKey(value)), content = content)
}

@Composable
fun YapchikScope(active: Boolean = true, blocking: Boolean = false, suppress: Boolean = false, content: @Composable () -> Unit) {
    val store = LocalStore.current
    val parent = LocalOwner.current
    val owner = remember { Any() }
    CompositionLocalProvider(LocalOwner provides owner, content = content)
    SideEffect { store?.updateOwner(owner, ActionOwner(parent, active, blocking, suppress)) }
    DisposableEffect(store, owner) { onDispose { store?.removeOwner(owner) } }
}

class ActionHandle internal constructor(
    private val store: ActionStore<ActionVisual>?,
    val identity: ActionIdentity,
    private val enabledState: State<Boolean>,
    private val selectedState: State<Boolean?>,
    private val callback: State<(() -> Unit)?>,
    private val lifecycle: Lifecycle,
    private val search: Boolean,
    private val control: String?,
) {
    private val lease = Any()
    private val visuals = linkedMapOf<Any, ActionVisual>()
    private var coordinates: LayoutCoordinates? = null
    private var attached = false
    private var boundCallback: State<(() -> Unit)?>? = null
    private var boundEnabled: State<Boolean>? = null
    private var boundSelected: State<Boolean>? = null
    private var boundToggle: State<((Boolean) -> Unit)?>? = null
    val onClick: () -> Unit = { (boundCallback?.value ?: callback.value)?.invoke() }
    private val activation: () -> (() -> Unit)? = {
        if (boundToggle != null) {
            val target = boundToggle?.value
            val checked = !(boundSelected?.value ?: selectedState.value ?: false)
            if (target == null) null else ({ target(checked) })
        } else boundCallback?.value ?: callback.value
    }
    private val available: () -> Boolean = {
        attached && activation() != null && lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED) && liveBounds()?.visible == true
    }

    @Composable
    fun bindNullable(value: (() -> Unit)?): (() -> Unit)? {
        val current = rememberUpdatedState(value)
        SideEffect { boundCallback = current; publish() }
        return value
    }

    @Composable
    fun bind(value: () -> Unit): () -> Unit {
        bindNullable(value)
        return value
    }

    @Composable
    fun bindNullableToggle(value: ((Boolean) -> Unit)?): ((Boolean) -> Unit)? {
        val current = rememberUpdatedState(value)
        SideEffect { boundToggle = current; publish() }
        return value
    }

    @Composable
    fun bindToggle(value: (Boolean) -> Unit): (Boolean) -> Unit {
        bindNullableToggle(value)
        return value
    }

    @Composable
    fun trackEnabled(value: Boolean): Boolean {
        val current = rememberUpdatedState(value)
        SideEffect { boundEnabled = current; publish() }
        return value
    }

    @Composable
    fun trackSelected(value: Boolean): Boolean {
        val current = rememberUpdatedState(value)
        SideEffect { boundSelected = current; publish() }
        return value
    }

    private fun liveBounds(): ActionBounds? {
        val current = coordinates?.takeIf { it.isAttached } ?: return null
        val bounds = current.boundsInWindow()
        return ActionBounds(bounds.left, bounds.top, bounds.right, bounds.bottom)
    }

    internal fun publish() {
        val presentation = visuals.values.toList().ifEmpty { control?.let { listOf(ActionVisual.Toggle(it)) } ?: emptyList() }
        store?.update(ActionReference(identity, lease, presentation, boundEnabled?.value ?: enabledState.value,
            boundSelected?.value ?: selectedState.value, search, if (available()) liveBounds() else null, available, activation))
    }

    internal fun visual(identity: Any, visual: ActionVisual?) {
        if (visual == null) visuals.remove(identity) else visuals[identity] = visual
        publish()
    }

    internal fun remove() { store?.remove(identity, lease) }

    val modifier: Modifier get() = Modifier.composed {
        DisposableEffect(this@ActionHandle) {
            attached = true
            onDispose { attached = false; coordinates = null; publish() }
        }
        SideEffect { publish() }
        Modifier.onGloballyPositioned { coordinates = it; publish() }
    }
}

@Composable
fun YapchikAction(
    source: String,
    onClick: (() -> Unit)?,
    enabled: Boolean = true,
    selected: Boolean? = null,
    search: Boolean = false,
    control: String? = null,
    content: @Composable (ActionHandle) -> Unit,
) {
    val store = LocalStore.current
    val owner = LocalOwner.current ?: remember { Any() }
    val keys = LocalItemKeys.current
    val instance = remember(source, keys) { Any() }
    val identity = ActionIdentity(owner, source, keys, instance)
    val currentCallback = rememberUpdatedState(onClick)
    val currentEnabled = rememberUpdatedState(enabled)
    val currentSelected = rememberUpdatedState(selected)
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val handle = remember(store, identity, lifecycle, search, control) {
        ActionHandle(store, identity, currentEnabled, currentSelected, currentCallback, lifecycle, search, control)
    }
    CompositionLocalProvider(LocalAction provides handle) { content(handle) }
    SideEffect { handle.publish() }
    DisposableEffect(handle, lifecycle) {
        val observer = LifecycleEventObserver { _, _ -> handle.publish() }
        lifecycle.addObserver(observer)
        onDispose { lifecycle.removeObserver(observer); handle.remove() }
    }
}

@Composable
fun <Value> YapchikText(value: Value, content: @Composable (Value) -> Unit) {
    val handle = LocalAction.current
    val identity = remember { Any() }
    val label = when (value) {
        is String -> value
        is AnnotatedString -> value.text
        is TextFieldValue -> value.text
        else -> null
    }
    content(value)
    SideEffect { handle?.visual(identity, label?.takeIf { it.isNotEmpty() }?.let { ActionVisual.Label(it) }) }
    DisposableEffect(handle, identity) { onDispose { handle?.visual(identity, null) } }
}

@Composable
fun <Value> YapchikIcon(value: Value, description: String?, content: @Composable (Value, String?) -> Unit) {
    val handle = LocalAction.current
    val identity = remember { Any() }
    content(value, description)
    val supported = value is ImageVector || value is ImageBitmap || value is Painter
    SideEffect { handle?.visual(identity, if (supported) ActionVisual.Glyph(value as Any, description) else null) }
    DisposableEffect(handle, identity) { onDispose { handle?.visual(identity, null) } }
}

private tailrec fun Context.activity(): Activity = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.activity()
    else -> error("Yapchik requires an Activity context")
}

@Composable
fun YapchikHost(content: @Composable () -> Unit) {
    val activity = LocalContext.current.activity()
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var revision by remember { mutableIntStateOf(0) }
    val store = remember { ActionStore<ActionVisual> { revision++ } }
    val owner = remember { Any() }
    var menuOpen by remember { mutableStateOf(false) }
    var active by remember { mutableStateOf(false) }
    var foreground by remember { mutableStateOf(lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)) }
    val theme = MaterialTheme.colorScheme
    DisposableEffect(activity, lifecycle) {
        if (!Yapchik.isInstalled) {
            Yapchik.autoDetector = { context -> app.vela.ui.isDpadFirstDevice(context) }
            Yapchik.install(activity.application)
        }
        val removeDiagnostics = attachKeyDiagnostics(activity)
        active = Yapchik.isActive
        val listener = Yapchik.StateListener { active = it }
        Yapchik.addStateListener(listener)
        val observer = LifecycleEventObserver { _, _ ->
            foreground = lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)
        }
        lifecycle.addObserver(observer)
        onDispose {
            removeDiagnostics()
            lifecycle.removeObserver(observer)
            Yapchik.removeStateListener(listener)
            store.removeOwner(owner)
            Softkeys.of(activity).clear()
        }
    }
    val currentRevision = revision
    val search = store.search()
    SideEffect {
        store.updateOwner(owner, ActionOwner(null, foreground, false, false))
        Yapchik.style.backgroundColor = theme.surface.toArgb()
        Yapchik.style.textColor = theme.onSurface.toArgb()
        Yapchik.style.pressedTextColor = theme.primary.toArgb()
        Yapchik.style.dividerColor = theme.outlineVariant.toArgb()
        Softkeys.of(activity).set {
            noDefaults()
            screenMode = if (active && foreground && !store.suppressed) SoftkeyMode.ON else SoftkeyMode.OFF
            if (active && foreground && !store.suppressed) {
                left("Options") { menuOpen = !menuOpen }
                if (search != null) right("Search") { store.dispatch(search.identity) { menuOpen = false } }
            }
        }
    }
    LaunchedEffect(active, foreground, currentRevision) {
        if (!active || !foreground || store.suppressed) menuOpen = false
    }
    Box(Modifier.fillMaxSize()) {
        CompositionLocalProvider(LocalStore provides store, LocalOwner provides owner) { content() }
        if (menuOpen && active && foreground && !store.suppressed) OptionsMenu(store) { menuOpen = false }
    }
}

@Composable
private fun OptionsMenu(store: ActionStore<ActionVisual>, dismiss: () -> Unit) {
    val entries = store.options()
    var focused by remember { mutableStateOf<ActionIdentity?>(null) }
    var previousIndex by remember { mutableIntStateOf(0) }
    val requester = remember { FocusRequester() }
    val scroll = rememberLazyListState()
    val identities = entries.map { it.identity }
    LaunchedEffect(identities) {
        focused = store.focus(focused, previousIndex)
        requester.requestFocus()
    }
    LaunchedEffect(focused, identities) {
        val index = identities.indexOf(focused)
        if (index >= 0) { previousIndex = index; scroll.scrollToItem(index) }
    }
    BackHandler(onBack = dismiss)
    Surface(Modifier.fillMaxSize().focusRequester(requester).onPreviewKeyEvent { event ->
        val native = event.nativeKeyEvent
        if (native.action != KeyEvent.ACTION_DOWN) false else when (native.keyCode) {
            KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN -> {
                if (entries.isNotEmpty()) {
                    val step = if (native.keyCode == KeyEvent.KEYCODE_DPAD_UP) -1 else 1
                    val index = identities.indexOf(focused).coerceAtLeast(0)
                    focused = identities[(index + step).coerceIn(0, entries.lastIndex)]
                }
                true
            }
            KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> {
                focused?.let { store.dispatch(it, dismiss) }
                true
            }
            else -> false
        }
    }.focusable()) {
        Column(Modifier.safeDrawingPadding().padding(8.dp)) {
            Text("Options", style = MaterialTheme.typography.titleMedium)
            if (entries.isEmpty()) Text("No actions available")
            LazyColumn(state = scroll) {
                items(entries, key = { store.lazyKey(it.identity) }) { reference ->
                    val highlighted = reference.identity == focused
                    Surface(
                        modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp)
                            .clickable(enabled = reference.enabled) { store.dispatch(reference.identity, dismiss) }
                            .semantics { reference.selected?.let { selected = it } },
                        border = if (highlighted) BorderStroke(2.dp, MaterialTheme.colorScheme.primary) else null,
                        color = if (highlighted) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surface,
                        contentColor = MaterialTheme.colorScheme.onSurface.copy(alpha = if (reference.enabled) 1f else 0.38f),
                    ) {
                        Row(Modifier.padding(10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            for (visual in reference.presentation) when (visual) {
                                is ActionVisual.Label -> Text(visual.text)
                                is ActionVisual.Glyph -> when (val icon = visual.value) {
                                    is ImageVector -> Icon(icon, visual.description)
                                    is ImageBitmap -> Icon(icon, visual.description)
                                    is Painter -> Icon(icon, visual.description)
                                }
                                is ActionVisual.Toggle -> when (visual.kind) {
                                    "RadioButton" -> RadioButton(selected = reference.selected == true, onClick = null, enabled = reference.enabled)
                                    "Switch" -> Switch(checked = reference.selected == true, onCheckedChange = null, enabled = reference.enabled)
                                    else -> Checkbox(checked = reference.selected == true, onCheckedChange = null, enabled = reference.enabled)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun YapchikPreferences() {
    val activity = LocalContext.current.activity()
    YapchikAction("yapchik-preferences", { YapchikSettingsDialog.show(activity) }) { action ->
        TextButton(onClick = action.onClick, modifier = action.modifier) {
            YapchikText("Hardware softkeys: mode and key calibration") { Text(it) }
        }
    }
}
