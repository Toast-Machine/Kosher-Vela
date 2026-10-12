package fixture

import androidx.compose.runtime.Composable

class DpadFocusKeeper {
    fun retarget() = Unit
}

@Composable
fun rememberDpadFocusKeeper(): DpadFocusKeeper {
    return DpadFocusKeeper()
}

@Composable
fun KeeperFactory(): DpadFocusKeeper = DpadFocusKeeper()

@Composable
fun InferredKeeperFactory() = DpadFocusKeeper()

@Composable
fun KeeperRow(keeper: DpadFocusKeeper) {
    keeper.retarget()
}

@Composable
fun ExplicitUnitRow(keeper: DpadFocusKeeper): Unit {
    keeper.retarget()
}

@Composable
fun RepeatedRows(values: List<String>) {
    values.forEach { value ->
        val remembered = rememberDpadFocusKeeper()
        val explicit = KeeperFactory()
        val inferred = InferredKeeperFactory()
        KeeperRow(remembered)
        ExplicitUnitRow(explicit)
        KeeperRow(inferred)
        remembered.retarget()
    }
    for (value in values) {
        val remembered = rememberDpadFocusKeeper()
        val explicit = KeeperFactory()
        val inferred = InferredKeeperFactory()
        KeeperRow(remembered)
        ExplicitUnitRow(explicit)
        KeeperRow(inferred)
        remembered.retarget()
    }
}
