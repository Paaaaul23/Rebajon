package com.rebajon.app

import android.Manifest
import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.webkit.JavascriptInterface
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.work.Constraints
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import java.util.concurrent.TimeUnit

fun prefs(c: Context) = c.getSharedPreferences("rebajon", Context.MODE_PRIVATE)

class Bridge(private val c: Context) {
    @JavascriptInterface fun getServer(): String = prefs(c).getString("server", "") ?: ""
    @JavascriptInterface fun setServer(u: String) {
        prefs(c).edit().putString("server", u.trim().trimEnd('/')).apply()
    }
    @JavascriptInterface fun openUrl(u: String) {
        if (u.startsWith("http")) {
            c.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(u)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
    }
}

class MainActivity : Activity() {
    private lateinit var web: WebView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 1)

        web = WebView(this)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.addJavascriptInterface(Bridge(this), "Android")
        web.webViewClient = WebViewClient()
        setContentView(web)
        web.loadUrl("file:///android_asset/index.html")

        val req = PeriodicWorkRequestBuilder<PriceWorker>(15, TimeUnit.MINUTES)
            .setConstraints(Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build())
            .build()
        WorkManager.getInstance(this)
            .enqueueUniquePeriodicWork("alerts", ExistingPeriodicWorkPolicy.KEEP, req)
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        web.evaluateJavascript("(window.goBack&&window.goBack())?1:0") { r ->
            if (r != "1") super.onBackPressed()
        }
    }
}
