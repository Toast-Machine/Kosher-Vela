package app.vela.yapchik

import androidx.compose.runtime.Composable

@Composable
fun YapchikItem(source: String, value: Any?, content: @Composable () -> Unit) {
    content()
}
