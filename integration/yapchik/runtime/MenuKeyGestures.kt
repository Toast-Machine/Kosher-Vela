package app.vela.yapchik

internal class MenuKeyGestures {
    private val captured = mutableSetOf<Int>()

    fun consume(key: Int, down: Boolean, menuOpen: Boolean): Boolean {
        if (down) {
            if (menuOpen) captured.add(key)
            return key in captured
        }
        return captured.remove(key) || menuOpen
    }
}
