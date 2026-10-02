package com.aircon.family;

import android.app.Application;
import android.content.Context;
import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;

public final class FamilyApplication extends Application {
    public static synchronized void initialize(Context context) {
        if (FirebaseApp.getApps(context).isEmpty()) {
            FirebaseApp.initializeApp(context, new FirebaseOptions.Builder()
                .setApplicationId(BuildConfig.FIREBASE_APP_ID).setApiKey(BuildConfig.FIREBASE_API_KEY)
                .setProjectId(BuildConfig.FIREBASE_PROJECT_ID).setGcmSenderId(BuildConfig.FIREBASE_SENDER_ID).build());
        }
    }
    @Override public void onCreate() {
        super.onCreate();
        if (BuildConfig.FLAVOR.equals("production")) initialize(this);
    }
}
