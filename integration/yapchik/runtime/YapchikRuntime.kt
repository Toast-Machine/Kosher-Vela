package app.vela.yapchik

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.view.KeyEvent
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.gestures.scrollBy
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.painter.Painter
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.layout.LayoutCoordinates
import androidx.compose.ui.layout.Placeable
import androidx.compose.ui.layout.SubcomposeLayout
import androidx.compose.ui.layout.boundsInWindow
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.isSpecified
import androidx.compose.ui.unit.sp
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.constrainHeight
import androidx.compose.ui.unit.constrainWidth
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.theonionsarewatching.yapchik.SoftkeyMode
import com.theonionsarewatching.yapchik.Softkeys
import com.theonionsarewatching.yapchik.Yapchik
import android.view.View
import android.view.ViewGroup
import android.view.ViewTreeObserver
import android.view.Window
import android.widget.TextView
import com.theonionsarewatching.yapchik.SoftkeyBar
import kotlin.math.ceil
import kotlin.math.roundToInt

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
    val menuHandler = remember { mutableStateOf<((KeyEvent) -> Unit)?>(null) }
    val currentMenuOpen = rememberUpdatedState(menuOpen)
    DisposableEffect(activity, lifecycle) {
        if (!Yapchik.isInstalled) {
            Yapchik.autoDetector = { context -> app.vela.ui.isDpadFirstDevice(context) }
            Yapchik.install(activity.application)
        }
        val removeDiagnostics = attachKeyDiagnostics(activity)
        Softkeys.of(activity)
        val window = activity.window
        val wrapped = window.callback
        val gestures = MenuKeyGestures()
        val gate = object : Window.Callback by wrapped {
            override fun dispatchKeyEvent(event: KeyEvent): Boolean {
                val menuKey = event.keyCode in listOf(KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN,
                    KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_NUMPAD_ENTER)
                if (menuKey && gestures.consume(event.keyCode, event.action == KeyEvent.ACTION_DOWN,
                        currentMenuOpen.value)) {
                    menuHandler.value?.invoke(event)
                    return true
                }
                return wrapped.dispatchKeyEvent(event)
            }
        }
        window.callback = gate
        active = Yapchik.isActive
        val listener = Yapchik.StateListener { active = it }
        Yapchik.addStateListener(listener)
        val observer = LifecycleEventObserver { _, _ ->
            foreground = lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)
        }
        lifecycle.addObserver(observer)
        onDispose {
            if (window.callback === gate) window.callback = wrapped
            removeDiagnostics()
            lifecycle.removeObserver(observer)
            Yapchik.removeStateListener(listener)
            store.removeOwner(owner)
            Softkeys.of(activity).clear()
        }
    }
    val currentRevision = revision
    val search = store.search()
    val optionsLabel = stringResource(app.vela.R.string.yapchik_options)
    val searchLabel = stringResource(app.vela.R.string.yapchik_search)
    DisposableEffect(activity) {
        // AUTO follows the navigation bar: showing or hiding it changes the window insets, which
        // lays the window out again.
        val decor = activity.window.decorView
        val listener = ViewTreeObserver.OnGlobalLayoutListener { NavBarSpaceSetting.apply(activity) }
        decor.viewTreeObserver.addOnGlobalLayoutListener(listener)
        onDispose { decor.viewTreeObserver.takeIf { it.isAlive }?.removeOnGlobalLayoutListener(listener) }
    }
    SideEffect {
        NavBarSpaceSetting.apply(activity)
        store.updateOwner(owner, ActionOwner(null, foreground, false, false))
        Yapchik.style.backgroundColor = theme.surface.toArgb()
        Yapchik.style.textColor = theme.onSurface.toArgb()
        Yapchik.style.pressedTextColor = theme.primary.toArgb()
        Yapchik.style.dividerColor = theme.outlineVariant.toArgb()
        Softkeys.of(activity).set {
            noDefaults()
            screenMode = if (active && foreground && !store.suppressed) SoftkeyMode.ON else SoftkeyMode.OFF
            if (active && foreground && !store.suppressed) {
                left(optionsLabel) { menuOpen = true }
                if (search != null) right(searchLabel) { store.dispatch(search.identity) { menuOpen = false } }
            }
        }
        applyBarTheme(activity.window.decorView)
    }
    LaunchedEffect(active, foreground, currentRevision) {
        if (!active || !foreground || store.suppressed) menuOpen = false
    }
    Box(Modifier.fillMaxSize()) {
        CompositionLocalProvider(LocalStore provides store, LocalOwner provides owner) { content() }
        if (menuOpen && active && foreground && !store.suppressed) OptionsMenu(store, menuHandler) { menuOpen = false }
    }
}

@Composable
private fun OptionsMenu(store: ActionStore<ActionVisual>, handler: MutableState<((KeyEvent) -> Unit)?>, dismiss: () -> Unit) {
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
        if (index < 0) return@LaunchedEffect
        previousIndex = index
        // Reveal the focused row with the smallest scroll. The row just below the bottom edge is
        // usually not laid out yet, because the row above it ends exactly at the edge: nudge it
        // into the layout, then align its bottom, so DOWN scrolls one row at a time like UP.
        repeat(3) {
            val layout = scroll.layoutInfo
            val rows = layout.visibleItemsInfo
            val visible = rows.firstOrNull { it.index == index }
            when {
                visible == null && rows.isNotEmpty() && index == rows.last().index + 1 ->
                    scroll.scrollBy((rows.last().offset + rows.last().size - layout.viewportEndOffset + 1).coerceAtLeast(1).toFloat())
                visible == null || visible.offset < layout.viewportStartOffset -> {
                    scroll.scrollToItem(index)
                    return@LaunchedEffect
                }
                visible.offset + visible.size > layout.viewportEndOffset -> {
                    scroll.scrollBy((visible.offset + visible.size - layout.viewportEndOffset).toFloat())
                    return@LaunchedEffect
                }
                else -> return@LaunchedEffect
            }
        }
    }
    BackHandler(onBack = dismiss)
    val currentHandler = rememberUpdatedState<(KeyEvent) -> Unit> { native ->
        when (native.keyCode) {
            KeyEvent.KEYCODE_DPAD_UP, KeyEvent.KEYCODE_DPAD_DOWN -> {
                if (native.action == KeyEvent.ACTION_DOWN && entries.isNotEmpty()) {
                    val step = if (native.keyCode == KeyEvent.KEYCODE_DPAD_UP) -1 else 1
                    val index = identities.indexOf(focused).coerceAtLeast(0)
                    focused = identities[(index + step).coerceIn(0, entries.lastIndex)]
                }
            }
            KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER, KeyEvent.KEYCODE_NUMPAD_ENTER -> {
                if (native.action == KeyEvent.ACTION_UP && !native.isCanceled)
                    focused?.let { store.dispatch(it, dismiss) }
            }
        }
    }
    DisposableEffect(handler) {
        handler.value = { currentHandler.value(it) }
        onDispose { handler.value = null }
    }
    val menuKeys = Modifier.focusRequester(requester).focusable()
    BoxWithConstraints(Modifier.fillMaxSize().safeDrawingPadding().padding(8.dp)) {
        Box(Modifier.fillMaxSize().clickable(
            interactionSource = remember { MutableInteractionSource() }, indication = null, onClick = dismiss,
        ))
        Surface(
            modifier = Modifier.align(Alignment.BottomStart).width(maxWidth / 2).heightIn(max = maxHeight * 3 / 4).then(menuKeys),
            shape = MaterialTheme.shapes.medium,
            border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
            shadowElevation = 6.dp,
        ) {
            Column(Modifier.padding(8.dp)) {
                Text(stringResource(app.vela.R.string.yapchik_options), style = MaterialTheme.typography.titleMedium)
                if (entries.isEmpty()) MenuEntry(listOf(ActionVisual.Label(stringResource(app.vela.R.string.yapchik_no_actions)))) {}
                LazyColumn(state = scroll, modifier = Modifier.weight(1f, fill = false)) {
                    items(entries, key = { store.lazyKey(it.identity) }) { reference ->
                        val highlighted = reference.identity == focused
                        Surface(
                            modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp)
                                .clickable(enabled = reference.enabled) { store.dispatch(reference.identity, dismiss) }
                                .semantics(mergeDescendants = true) { reference.selected?.let { selected = it } },
                            border = if (highlighted) BorderStroke(2.dp, MaterialTheme.colorScheme.primary) else null,
                            color = if (highlighted) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surface,
                            contentColor = MaterialTheme.colorScheme.onSurface.copy(alpha = if (reference.enabled) 1f else 0.38f),
                        ) {
                            Box(Modifier.padding(10.dp)) {
                                MenuEntry(menuPresentation(reference.presentation)) { visual ->
                                    when (visual) {
                                        is ActionVisual.Label -> Unit
                                        is ActionVisual.Glyph -> when (val icon = visual.value) {
                                            is ImageVector -> Icon(icon, visual.description)
                                            is ImageBitmap -> Icon(icon, visual.description)
                                            is Painter -> Icon(icon, visual.description)
                                            else -> Unit
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
    }
}

/**
 * One Options row. Icons and toggles keep their full size; the row's labels (a title and its
 * subtitle) become one text, the subtitle dimmed, that wraps as a whole in the remaining width.
 * The row is as tall as its tallest full-size part (a one-line full-size label counts), and the
 * text takes the largest scale whose word-wrapped lines fit that height: it shrinks only until
 * another line fits, then wraps instead of shrinking further. Only when the full-size icons alone
 * are wider than the menu does the whole row scale down uniformly.
 */
@Composable
private fun MenuEntry(visuals: List<ActionVisual>, fixed: @Composable (ActionVisual) -> Unit) {
    val measurer = rememberTextMeasurer()
    val base = LocalTextStyle.current.let { if (it.fontSize.isSpecified) it else it.copy(fontSize = 14.sp) }
    val secondary = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = LocalContentColor.current.alpha)
    val labels = visuals.mapNotNull { (it as? ActionVisual.Label)?.text?.takeIf { it.isNotBlank() } }
    val text = remember(labels, secondary) {
        buildAnnotatedString {
            labels.forEachIndexed { index, label ->
                if (index == 0) append(label) else {
                    append(" ")
                    withStyle(SpanStyle(color = secondary)) { append(label) }
                }
            }
        }
    }
    val labelIndex = if (labels.isEmpty()) -1 else visuals.indexOfFirst { it is ActionVisual.Label && it.text.isNotBlank() }
    SubcomposeLayout { constraints ->
        val gap = 8.dp.roundToPx()
        val fixedParts = HashMap<Int, Placeable>()
        visuals.forEachIndexed { index, visual ->
            if (visual !is ActionVisual.Label) subcompose(index) { fixed(visual) }.firstOrNull()?.let {
                fixedParts[index] = it.measure(Constraints())
            }
        }
        val label = if (labelIndex < 0) null else {
            val oneLine = measurer.measure(text, base, maxLines = 1, softWrap = false).size
            val segment = unbreakableSegments(text.text)
                .maxOfOrNull { measurer.measure(it, base, maxLines = 1, softWrap = false).size.width } ?: 0
            val height = maxOf(fixedParts.values.maxOfOrNull { it.height } ?: 0, oneLine.height)
            val width = if (!constraints.hasBoundedWidth) oneLine.width
                else (constraints.maxWidth - fixedParts.values.sumOf { it.width } - gap * fixedParts.size).coerceAtLeast(0)
            fun style(scale: Float) = base.copy(
                fontSize = base.fontSize * scale,
                lineHeight = if (base.lineHeight.isSpecified) base.lineHeight * scale else base.lineHeight,
            )
            val scale = largestFittingScale { scale ->
                segment * scale <= width &&
                    measurer.measure(text, style(scale), constraints = Constraints(maxWidth = width)).size.height <= height
            }
            val textStyle = style(scale)
            subcompose("label") { Text(text, style = textStyle) }.first().measure(Constraints(maxWidth = width))
        }
        val parts = visuals.indices.mapNotNull { if (it == labelIndex) label else fixedParts[it] }
        val rowWidth = parts.sumOf { it.width } + gap * (parts.size - 1).coerceAtLeast(0)
        val rowHeight = parts.maxOfOrNull { it.height } ?: 0
        val shrink = if (constraints.hasBoundedWidth) menuContentScale(rowWidth, constraints.maxWidth) else 1f
        layout(constraints.constrainWidth(ceil(rowWidth * shrink).toInt()), constraints.constrainHeight(ceil(rowHeight * shrink).toInt())) {
            var x = 0
            for (part in parts) {
                part.placeRelativeWithLayer((x * shrink).roundToInt(), ((rowHeight - part.height) / 2 * shrink).roundToInt()) {
                    scaleX = shrink
                    scaleY = shrink
                    transformOrigin = TransformOrigin(0f, 0f)
                }
                x += part.width + gap
            }
        }
    }
}

private fun applyBarTheme(view: View) {
    if (view is SoftkeyBar) {
        view.setBackgroundColor(Yapchik.style.backgroundColor)
        view.getChildAt(0)?.setBackgroundColor(Yapchik.style.dividerColor)
        fun labels(child: View) {
            if (child is TextView) child.setTextColor(Yapchik.style.textColor)
            if (child is ViewGroup) for (index in 0 until child.childCount) labels(child.getChildAt(index))
        }
        labels(view)
    } else if (view is ViewGroup) for (index in 0 until view.childCount) applyBarTheme(view.getChildAt(index))
}
