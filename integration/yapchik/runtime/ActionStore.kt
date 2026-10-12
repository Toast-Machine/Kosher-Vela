package app.vela.yapchik

data class ActionBounds(val left: Float, val top: Float, val right: Float, val bottom: Float) {
    val visible: Boolean get() = right > left && bottom > top
}

data class ActionIdentity(val owner: Any, val source: String, val itemKeys: List<Any>, val instance: Any?)

data class ActionOwner(val parent: Any?, val active: Boolean, val blocking: Boolean, val suppress: Boolean)

data class ActionReference<Visual>(
    val identity: ActionIdentity,
    val lease: Any,
    val presentation: List<Visual>,
    val enabled: Boolean,
    val selected: Boolean?,
    val search: Boolean,
    val bounds: ActionBounds?,
    val available: () -> Boolean,
    val activation: () -> (() -> Unit)?,
)

class ActionStore<Visual>(private val changed: () -> Unit = {}) {
    private val actions = linkedMapOf<ActionIdentity, ActionReference<Visual>>()
    private val lazyKeys = mutableMapOf<ActionIdentity, Long>()
    private var nextLazyKey = 0L
    private val owners = linkedMapOf<Any, ActionOwner>()

    fun updateOwner(identity: Any, owner: ActionOwner) {
        if (owners[identity] != owner) {
            owners[identity] = owner
            changed()
        }
    }

    fun removeOwner(identity: Any) {
        if (owners.remove(identity) != null) changed()
    }

    fun update(reference: ActionReference<Visual>) {
        if (actions[reference.identity] != reference) {
            lazyKeys.getOrPut(reference.identity) { nextLazyKey++ }
            actions[reference.identity] = reference
            changed()
        }
    }

    fun lazyKey(identity: ActionIdentity): Long = lazyKeys.getValue(identity)

    fun remove(identity: ActionIdentity, lease: Any) {
        if (actions[identity]?.lease === lease) {
            actions.remove(identity)
            lazyKeys.remove(identity)
            changed()
        }
    }

    private fun active(identity: Any): Boolean {
        val owner = owners[identity] ?: return false
        return owner.active && (owner.parent == null || active(owner.parent))
    }

    private fun belongsTo(identity: Any, ancestor: Any): Boolean {
        if (identity == ancestor) return true
        val parent = owners[identity]?.parent ?: return false
        return belongsTo(parent, ancestor)
    }

    private fun blockingOwner(): Any? = owners.entries.lastOrNull { it.value.blocking && active(it.key) }?.key

    val suppressed: Boolean get() = owners.any { it.value.suppress && active(it.key) }

    fun entries(): List<ActionReference<Visual>> {
        if (suppressed) return emptyList()
        val blocker = blockingOwner()
        return actions.values.filter { reference ->
            active(reference.identity.owner) && (blocker == null || belongsTo(reference.identity.owner, blocker)) &&
                reference.bounds?.visible == true && reference.available() && reference.presentation.isNotEmpty()
        }.sortedWith(compareBy({ it.bounds!!.top }, { it.bounds!!.left }, { it.identity.source }))
    }

    fun search(): ActionReference<Visual>? = entries().firstOrNull { it.search }

    fun options(): List<ActionReference<Visual>> {
        val right = search()?.identity
        return entries().filter { it.identity != right }
    }

    fun dispatch(identity: ActionIdentity, dismiss: () -> Unit): Boolean {
        val current = entries().firstOrNull { it.identity == identity && it.enabled } ?: return false
        val callback = current.activation() ?: return false
        dismiss()
        callback()
        return true
    }

    fun focus(previous: ActionIdentity?, previousIndex: Int = 0): ActionIdentity? {
        val current = options()
        return current.firstOrNull { it.identity == previous }?.identity
            ?: current.getOrNull(previousIndex.coerceIn(0, (current.size - 1).coerceAtLeast(0)))?.identity
    }
}
