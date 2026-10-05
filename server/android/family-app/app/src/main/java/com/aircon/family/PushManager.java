package com.aircon.family;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.Context;
import android.content.SharedPreferences;
import androidx.work.*;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseUser;
import com.google.firebase.messaging.FirebaseMessaging;
import org.json.JSONObject;
import java.security.SecureRandom;
import java.util.UUID;

/** Installation proof stays in private, non-backed-up app storage; never printed. */
final class PushManager {
    static final String CHANNEL="family_events", CLIMATE_CHANNEL="family_climate", WORK="family-push-registration";
    static SharedPreferences prefs(Context c) { return c.getSharedPreferences("push",0); }
    static synchronized String installation(Context c) {
        SharedPreferences p=prefs(c);
        if (!p.contains("installation")) {
            byte[] random=new byte[32]; new SecureRandom().nextBytes(random);
            StringBuilder hex=new StringBuilder(); for(byte b:random) hex.append(String.format("%02x",b&255));
            p.edit().putString("installation",UUID.randomUUID().toString()).putString("secret",hex.toString()).commit();
        }
        return p.getString("installation","");
    }
    static void channel(Context c) {
        c.getSystemService(NotificationManager.class).createNotificationChannel(
            new NotificationChannel(CHANNEL,"우리 집 알림",NotificationManager.IMPORTANCE_DEFAULT));
        c.getSystemService(NotificationManager.class).createNotificationChannel(
            new NotificationChannel(CLIMATE_CHANNEL,"온습도 알림",NotificationManager.IMPORTANCE_LOW));
    }
    static synchronized void enable(Context c,String origin,String account) {
        installation(c); channel(c);
        SharedPreferences p=prefs(c);
        if (!account.equals(p.getString("account","")) || !origin.equals(p.getString("origin","")))
            p.edit().remove("binding").putString("epoch",UUID.randomUUID().toString()).commit();
        p.edit().putBoolean("enabled",true).putString("account",account).putString("origin",origin)
            .putBoolean("registration_error",false).remove("registration_error_message").commit();
        FirebaseMessaging.getInstance().setAutoInitEnabled(true); sync(c);
    }
    static synchronized void preferences(Context c,boolean door,boolean climate,boolean warning,int interval) {
        if(interval!=1 && interval!=5 && interval!=15 && interval!=60) throw new IllegalArgumentException();
        prefs(c).edit().putBoolean("door",door).putBoolean("climate",climate).putBoolean("warning",warning)
            .putInt("climate_interval_minutes",interval).putBoolean("preferences_pending",true)
            .putBoolean("registration_error",false).remove("registration_error_message")
            .putString("epoch",UUID.randomUUID().toString()).commit();
        sync(c);
    }
    static boolean categoryAllowed(SharedPreferences p,String category) {
        if(category==null || category.equals("other")) return true;
        if(category.equals("door") || category.equals("climate") || category.equals("warning"))
            return p.getBoolean(category,!category.equals("climate"));
        return false;
    }
    static void sync(Context c) {
        if (!BuildConfig.FLAVOR.equals("production") || !prefs(c).getBoolean("enabled",false)) return;
        OneTimeWorkRequest work=new OneTimeWorkRequest.Builder(PushSyncWorker.class)
            .setConstraints(new Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()).build();
        WorkManager.getInstance(c).enqueueUniqueWork(WORK,ExistingWorkPolicy.APPEND_OR_REPLACE,work);
    }
    static synchronized void disable(Context c) {
        if (!BuildConfig.FLAVOR.equals("production")) return;
        SharedPreferences p=prefs(c); String origin=p.getString("origin","");
        String id=installation(c),secret=p.getString("secret",""),binding=p.getString("binding","");
        p.edit().putBoolean("enabled",false).remove("binding").putString("epoch",UUID.randomUUID().toString()).commit();
        c.getSystemService(NotificationManager.class).cancelAll();
        WorkManager.getInstance(c).cancelUniqueWork(WORK);
        FirebaseMessaging.getInstance().setAutoInitEnabled(false);
        FirebaseUser user=FirebaseAuth.getInstance().getCurrentUser();
        if (user!=null && !origin.isEmpty() && !binding.isEmpty()) user.getIdToken(false).addOnSuccessListener(result -> {
            new Thread(()-> {
                try { new ApiClient(origin,BuildConfig.DEBUG).request(result.getToken(),"POST","/v1/installations/"+id+"/unregister",
                    new JSONObject().put("secret",secret).put("binding",binding)); } catch(Exception ignored) { /* local gate remains closed offline */ }
            },"push-unregister").start();
        });
    }
}
