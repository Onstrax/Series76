package com.series76.assistant

import android.app.Application

/** Holds the single [AppContainer] for the process. */
class Series76App : Application() {
    lateinit var container: AppContainer
        private set

    override fun onCreate() {
        super.onCreate()
        container = AppContainer(this)
    }
}
