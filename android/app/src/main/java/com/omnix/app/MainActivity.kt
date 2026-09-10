package com.omnix.app

import android.content.Intent
import android.os.Bundle
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import androidx.webkit.WebViewAssetLoader
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import com.omnix.billing.PlayBillingBridge
import java.lang.ref.WeakReference
import org.json.JSONObject

class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView
    private val assetLoader by lazy {
        WebViewAssetLoader.Builder()
            .addPathHandler("/assets/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()
    }

    companion object {
        private var webViewRef: WeakReference<WebView>? = null
        private var launchPayloadJson: String? = null
        private var pendingPushToken: String? = null

        fun cacheLaunchPayload(payloadJson: String?) {
            if (!payloadJson.isNullOrBlank()) launchPayloadJson = payloadJson
        }

        fun cachePushToken(token: String?) {
            if (!token.isNullOrBlank()) pendingPushToken = token
        }

        fun dispatchToWeb(payloadJson: String) {
            cacheLaunchPayload(payloadJson)
            webViewRef?.get()?.post {
                val escaped = JSONObject.quote(payloadJson)
                webViewRef?.get()?.evaluateJavascript(
                    "window.dispatchEvent(new CustomEvent('omnix-open-screen', { detail: JSON.parse($escaped) }));",
                    null,
                )
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        installSplashScreen()
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        launchPayloadJson = buildLaunchPayload(intent)
        webView = findViewById(R.id.appWebView)
        webViewRef = WeakReference(webView)
        configureWebView()

        initializeFirebaseMessagingSafely()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        val payload = buildLaunchPayload(intent)
        if (!payload.isNullOrBlank()) dispatchToWeb(payload)
    }

    fun peekLaunchPayload(): String? = launchPayloadJson

    fun clearLaunchPayload() { launchPayloadJson = null }

    fun peekPendingPushToken(): String? = pendingPushToken

    fun clearPendingPushToken() { pendingPushToken = null }

    private fun initializeFirebaseMessagingSafely() {
        // Firebase is optional for local/debug builds. A missing google-services
        // configuration must never prevent the core app/WebView from starting.
        try {
            if (FirebaseApp.getApps(this).isEmpty()) return
            FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
                if (task.isSuccessful) cachePushToken(task.result)
            }
        } catch (_: Exception) {
            // Push notifications are non-critical; keep the app usable without them.
        }
    }

    private fun configureWebView() {
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.mediaPlaybackRequiresUserGesture = false
        webView.settings.allowFileAccess = true
        webView.settings.allowContentAccess = true
        webView.addJavascriptInterface(AndroidAppBridge(this), "AndroidAppBridge")
        webView.addJavascriptInterface(AndroidSecureBridge(this), "AndroidSecureBridge")
        webView.addJavascriptInterface(BiometricBridge(this), "AndroidBiometricBridge")
        webView.addJavascriptInterface(PlayBillingBridge(this), "AndroidBilling")
        webView.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(view: WebView?, request: WebResourceRequest): WebResourceResponse? {
                return assetLoader.shouldInterceptRequest(request.url)
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                launchPayloadJson?.let { dispatchToWeb(it) }
            }
        }

        if (assetExists("www/index.html")) {
            webView.loadUrl(BuildConfig.WEB_APP_START_URL)
        } else {
            webView.loadUrl(BuildConfig.WEB_APP_FALLBACK_URL)
        }
    }

    private fun assetExists(path: String): Boolean {
        return try {
            assets.open(path).close()
            true
        } catch (_: Exception) {
            false
        }
    }

    private fun buildLaunchPayload(intent: Intent?): String? {
        if (intent == null) return null
        val targetScreen = intent.getStringExtra("targetScreen") ?: intent.data?.getQueryParameter("targetScreen")
        val conversationId = intent.getStringExtra("conversationId") ?: intent.data?.getQueryParameter("conversationId")
        val profileId = intent.getStringExtra("profileId") ?: intent.data?.getQueryParameter("profileId")
        val notificationType = intent.getStringExtra("notificationType") ?: intent.data?.getQueryParameter("notificationType")
        if (targetScreen == null && conversationId == null && profileId == null) return null
        return JSONObject()
            .put("targetScreen", targetScreen)
            .put("conversationId", conversationId)
            .put("profileId", profileId)
            .put("notificationType", notificationType)
            .toString()
    }
}
