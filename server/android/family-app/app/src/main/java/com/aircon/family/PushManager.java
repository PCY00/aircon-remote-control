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
import java.util.Calendar;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/** Installation proof stays in private, non-backed-up app storage; never printed. */
final class PushManager {
    static final String CHANNEL=AlertLevels.CHANNEL_EVENTS, CLIMATE_CHANNEL=AlertLevels.CHANNEL_REPORT,
        URGENT_CHANNEL=AlertLevels.CHANNEL_URGENT, QUIET_CHANNEL=AlertLevels.CHANNEL_QUIET, WORK="family-push-registration";
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
        NotificationManager manager=c.getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL,"우리 집 알림",NotificationManager.IMPORTANCE_DEFAULT));
        manager.createNotificationChannel(new NotificationChannel(CLIMATE_CHANNEL,"온습도 알림",NotificationManager.IMPORTANCE_LOW));
        manager.createNotificationChannel(new NotificationChannel(URGENT_CHANNEL,"긴급 알림",NotificationManager.IMPORTANCE_HIGH));
        manager.createNotificationChannel(new NotificationChannel(QUIET_CHANNEL,"방해 금지 시간 알림",NotificationManager.IMPORTANCE_LOW));
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
    /** Moves the 0.6 door/climate/warning switches and the climate interval to levels once. */
    private static void migrate(SharedPreferences p) {
        if(p.getBoolean("levels_migrated",false)) return;
        Map<String,String> levels=AlertLevels.migrate(p.getBoolean("door",true),p.getBoolean("climate",false),p.getBoolean("warning",true));
        SharedPreferences.Editor edit=p.edit();
        for(Map.Entry<String,String> entry:levels.entrySet()) edit.putString("level_"+entry.getKey(),entry.getValue());
        int interval=p.getInt("climate_interval_minutes",5);
        edit.putInt("report_interval_minutes",AlertLevels.validInterval(interval) ? interval : 5).putBoolean("levels_migrated",true).commit();
    }
    static synchronized String level(SharedPreferences p,String category) {
        migrate(p);
        String level=p.getString("level_"+category,AlertLevels.defaultLevel(category));
        return AlertLevels.valid(category,level) ? level : AlertLevels.defaultLevel(category);
    }
    /** All seven categories, as the server wants them every time. */
    static synchronized Map<String,String> levels(SharedPreferences p) {
        Map<String,String> levels=new LinkedHashMap<>();
        for(String category:AlertLevels.CATEGORIES) levels.put(category,level(p,category));
        return levels;
    }
    static synchronized int reportInterval(SharedPreferences p) {
        migrate(p);
        int interval=p.getInt("report_interval_minutes",5);
        return AlertLevels.validInterval(interval) ? interval : 5;
    }
    /** Saves one level for this phone and re-sends the whole table; other phones keep theirs. */
    static synchronized void level(Context c,String category,String level) {
        if(!AlertLevels.valid(category,level)) throw new IllegalArgumentException();
        migrate(prefs(c)); changed(c,prefs(c).edit().putString("level_"+category,level));
    }
    static synchronized void reportInterval(Context c,int minutes) {
        if(!AlertLevels.validInterval(minutes)) throw new IllegalArgumentException();
        migrate(prefs(c)); changed(c,prefs(c).edit().putInt("report_interval_minutes",minutes));
    }
    private static void changed(Context c,SharedPreferences.Editor edit) {
        edit.putBoolean("preferences_pending",true).putBoolean("registration_error",false).remove("registration_error_message")
            .putString("epoch",UUID.randomUUID().toString()).commit();
        sync(c);
    }
    static boolean quietEnabled(SharedPreferences p) { return p.getBoolean("quiet_enabled",false); }
    static int quietStart(SharedPreferences p) { return p.getInt("quiet_start",AlertLevels.QUIET_START); }
    static int quietEnd(SharedPreferences p) { return p.getInt("quiet_end",AlertLevels.QUIET_END); }
    /** Do-not-disturb hours follow this phone's clock and never leave the phone. */
    static synchronized void quietHours(Context c,boolean enabled,int start,int end) {
        if(start<0 || start>=1440 || end<0 || end>=1440) throw new IllegalArgumentException();
        prefs(c).edit().putBoolean("quiet_enabled",enabled).putInt("quiet_start",start).putInt("quiet_end",end).commit();
    }
    static boolean inQuietHours(SharedPreferences p,Calendar now) {
        return quietEnabled(p) && AlertLevels.inQuietHours(quietStart(p),quietEnd(p),now.get(Calendar.HOUR_OF_DAY)*60+now.get(Calendar.MINUTE));
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
                try { new ApiClient(c,origin,BuildConfig.DEBUG).request(result.getToken(),"POST","/v1/installations/"+id+"/unregister",
                    new JSONObject().put("secret",secret).put("binding",binding)); } catch(Exception ignored) { /* local gate remains closed offline */ }
            },"push-unregister").start();
        });
    }
}
