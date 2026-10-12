plugins {
    alias(libs.plugins.android.library)
}

android {
    namespace = "com.theonionsarewatching.yapchik"
    compileSdk = 37
    defaultConfig {
        minSdk = 21
        consumerProguardFiles("consumer-rules.pro")
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
