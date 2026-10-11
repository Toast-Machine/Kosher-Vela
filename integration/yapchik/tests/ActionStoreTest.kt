package app.vela.yapchik

import org.junit.Assert.*
import org.junit.Test

class ActionStoreTest {
    private val owner = "screen"
    private val bounds = ActionBounds(0f, 0f, 40f, 40f)

    private fun store(): ActionStore<String> = ActionStore<String>().also {
        it.updateOwner(owner, ActionOwner(null, true, false, false))
    }

    private fun entry(
        name: String,
        search: Boolean = false,
        enabled: Boolean = true,
        item: String = name,
        available: () -> Boolean = { true },
        callback: () -> Unit = {},
    ): ActionReference<String> = ActionReference(
        ActionIdentity(owner, name, listOf(item), null), Any(), listOf(name), enabled, null,
        search, bounds, available, { callback },
    )

    @Test fun duplicateItemKeysRemainSeparateCompositionInstances() {
        val store = store()
        val first = entry("Run", item = "duplicate")
        val second = first.copy(identity = first.identity.copy(instance = Any()), lease = Any())
        store.update(first)
        store.update(second)
        assertEquals(2, store.options().size)
        store.remove(first.identity, first.lease)
        assertEquals(listOf(second.identity), store.options().map { it.identity })
    }

    @Test fun rightSearchIsExcludedByIdentityNotLabel() {
        val store = store()
        val right = entry("Search", search = true)
        val other = entry("Search", item = "other")
        store.update(right)
        store.update(other)
        assertEquals(right.identity, store.search()?.identity)
        assertEquals(listOf(other.identity), store.options().map { it.identity })
    }

    @Test fun currentHandlerRunsExactlyOnceAfterDismissal() {
        val store = store()
        val events = mutableListOf<String>()
        val old = entry("Go", callback = { events.add("old") })
        store.update(old)
        store.update(old.copy(activation = { { events.add("current") } }))
        assertTrue(store.dispatch(old.identity) { events.add("dismiss"); store.remove(old.identity, old.lease) })
        assertEquals(listOf("dismiss", "current"), events)
    }

    @Test fun dismissalCannotSwitchCapturedCallback() {
        val store = store()
        var called = ""
        var callback: () -> Unit = { called = "original" }
        val action = entry("Go").copy(activation = { callback })
        store.update(action)
        store.dispatch(action.identity) { callback = { called = "replacement" } }
        assertEquals("original", called)
    }

    @Test fun disabledControlsRemainListedButCannotRun() {
        val store = store()
        val action = entry("Go", enabled = false, callback = { fail("Disabled action invoked") })
        store.update(action)
        assertEquals(1, store.options().size)
        assertFalse(store.dispatch(action.identity) { fail("Disabled action dismissed menu") })
    }

    @Test fun visibilityIsRevalidatedAtActivation() {
        val store = store()
        var visible = true
        val action = entry("Go", available = { visible }, callback = { fail("Invisible action invoked") })
        store.update(action)
        visible = false
        assertTrue(store.options().isEmpty())
        assertFalse(store.dispatch(action.identity) {})
    }

    @Test fun fullyClippedControlsAreExcluded() {
        val store = store()
        store.update(entry("Go").copy(bounds = ActionBounds(1f, 1f, 1f, 4f)))
        assertTrue(store.options().isEmpty())
    }

    @Test fun inactiveScreenDoesNotLeakActions() {
        val store = store()
        store.update(entry("Go"))
        store.updateOwner(owner, ActionOwner(null, false, false, false))
        assertTrue(store.entries().isEmpty())
        assertNull(store.search())
    }

    @Test fun blockingPanelExcludesUnderlyingActions() {
        val store = store()
        store.update(entry("Map"))
        store.updateOwner("panel", ActionOwner(owner, true, true, false))
        val panel = entry("Panel").let { it.copy(identity = it.identity.copy(owner = "panel")) }
        store.update(panel)
        assertEquals(listOf("Panel"), store.options().map { it.presentation.single() })
        store.removeOwner("panel")
        assertEquals(listOf("Map"), store.options().map { it.presentation.single() })
    }

    @Test fun nativeDialogSuppressesBarAndUnderlyingMenu() {
        val store = store()
        store.update(entry("Map"))
        store.updateOwner("dialog", ActionOwner(owner, true, true, true))
        assertTrue(store.suppressed)
        assertTrue(store.entries().isEmpty())
        store.removeOwner("dialog")
        assertFalse(store.suppressed)
        assertEquals(1, store.entries().size)
    }

    @Test fun staleCompositionCannotRemoveReplacementInstance() {
        val store = store()
        val old = entry("Go")
        val replacement = entry("Go")
        store.update(old)
        store.update(replacement)
        store.remove(old.identity, old.lease)
        assertEquals(replacement.lease, store.options().single().lease)
    }

    @Test fun focusFollowsIdentityWhenItemsReorder() {
        val store = store()
        val first = entry("First")
        val second = entry("Second").copy(bounds = ActionBounds(0f, 50f, 40f, 90f))
        store.update(first)
        store.update(second)
        store.update(first.copy(bounds = ActionBounds(0f, 100f, 40f, 140f)))
        assertEquals(first.identity, store.focus(first.identity))
        store.remove(first.identity, first.lease)
        assertEquals(second.identity, store.focus(first.identity, 1))
    }

    @Test fun selectedStateAndPresentationUpdateWithoutChangingIdentity() {
        val store = store()
        val first = entry("Toggle")
        store.update(first)
        store.update(first.copy(presentation = listOf("Updated"), selected = true))
        val current = store.options().single()
        assertEquals(first.identity, current.identity)
        assertEquals(true, current.selected)
        assertEquals(listOf("Updated"), current.presentation)
    }
}
