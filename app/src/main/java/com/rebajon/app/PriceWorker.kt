package com.rebajon.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.work.Worker
import androidx.work.WorkerParameters
import org.json.JSONArray
import java.net.HttpURLConnection
import java.net.URL

class PriceWorker(ctx: Context, p: WorkerParameters) : Worker(ctx, p) {
    override fun doWork(): Result {
        val sp = prefs(applicationContext)
        val server = sp.getString("server", "") ?: ""
        if (server.isEmpty()) return Result.success()
        return try {
            val last = sp.getLong("last", -1L)
            val conn = URL("$server/alerts?since=${if (last < 0) 0 else last}").openConnection() as HttpURLConnection
            conn.connectTimeout = 15000
            conn.readTimeout = 15000
            val arr = JSONArray(conn.inputStream.bufferedReader().use { it.readText() })
            conn.disconnect()
            var max = if (last < 0) 0L else last
            // primera ejecución: no inundar con alertas antiguas
            val first = last < 0
            val nm = applicationContext.getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(NotificationChannel("ofertas", "Ofertas", NotificationManager.IMPORTANCE_HIGH))
            val pi = PendingIntent.getActivity(
                applicationContext, 0, Intent(applicationContext, MainActivity::class.java), PendingIntent.FLAG_IMMUTABLE
            )
            for (i in 0 until arr.length()) {
                val a = arr.getJSONObject(i)
                val id = a.getLong("id")
                if (!first) {
                    nm.notify(id.toInt(), Notification.Builder(applicationContext, "ofertas")
                        .setSmallIcon(R.drawable.ic_logo)
                        .setContentTitle(a.getString("title"))
                        .setContentText(a.getString("body"))
                        .setContentIntent(pi).setAutoCancel(true).build())
                }
                if (id > max) max = id
            }
            sp.edit().putLong("last", max).apply()
            Result.success()
        } catch (e: Exception) {
            Result.retry()
        }
    }
}
