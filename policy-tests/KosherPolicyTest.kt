package app.vela.ui

import android.content.ContextWrapper
import androidx.compose.runtime.MutableState
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class KosherPolicyTest {
    @Test
    fun lockedSettingsIgnoreInitializationAndAttemptsToChangeThem() {
        val context = ContextWrapper(null)
        ShowReviews.init(context)
        LoadPhotos.init(context)
        LiveReviews.init(context)
        HideExternalLinks.init(context)
        for (attempt in listOf(true, false, true)) {
            ShowReviews.set(context, attempt)
            LoadPhotos.set(context, attempt)
            LiveReviews.set(context, attempt)
            HideExternalLinks.set(context, attempt)
            assertFalse(ShowReviews.on.value)
            assertFalse(LoadPhotos.on.value)
            assertFalse(LiveReviews.on.value)
            assertTrue(HideExternalLinks.on.value)
        }
        assertFalse(ShowReviews.on is MutableState<*>)
        assertFalse(LoadPhotos.on is MutableState<*>)
        assertFalse(LiveReviews.on is MutableState<*>)
        assertFalse(HideExternalLinks.on is MutableState<*>)
    }
}
