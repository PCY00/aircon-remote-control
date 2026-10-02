package com.aircon.family;

import android.content.Context;
import android.content.SharedPreferences;
import androidx.work.Worker;
import androidx.work.WorkerParameters;
import com.google.android.gms.tasks.Tasks;
import com.google.firebase.auth.*;
import com.google.firebase.messaging.FirebaseMessaging;
import org.json.JSONObject;
import java.util.concurrent.TimeUnit;

public final class PushSyncWorker extends Worker {
    public PushSyncWorker(Context c,WorkerParameters p) { super(c,p); }
    @Override public Result doWork() {
        Context c=getApplicationContext(); SharedPreferences p=PushManager.prefs(c);
        String epoch=p.getString("epoch",""),account=p.getString("account",""),origin=p.getString("origin","");
        if(!BuildConfig.FLAVOR.equals("production") || !p.getBoolean("enabled",false) || origin.isEmpty()) return Result.success();
        FirebaseUser user=FirebaseAuth.getInstance().getCurrentUser();
        if(user==null || !account.equals(user.getUid())) return Result.success();
        String id=PushManager.installation(c),secret=p.getString("secret","");
        try {
            String fcm=Tasks.await(FirebaseMessaging.getInstance().getToken(),20,TimeUnit.SECONDS);
            String auth=Tasks.await(user.getIdToken(false),20,TimeUnit.SECONDS).getToken();
            if(!p.getBoolean("enabled",false) || !epoch.equals(p.getString("epoch",""))) return Result.success();
            JSONObject reply=new ApiClient(origin,BuildConfig.DEBUG).request(auth,"PUT","/v1/installations/"+id,
                new JSONObject().put("secret",secret).put("token",fcm));
            if(p.getBoolean("enabled",false) && epoch.equals(p.getString("epoch",""))) {
                new ApiClient(origin,BuildConfig.DEBUG).request(auth,"PUT","/v1/installations/"+id+"/preferences",
                    new JSONObject().put("secret",secret).put("door",p.getBoolean("door",true))
                    .put("climate",p.getBoolean("climate",false)).put("warning",p.getBoolean("warning",true))
                    .put("climate_interval_minutes",p.getInt("climate_interval_minutes",5)));
            }
            synchronized(PushManager.class) {
                FirebaseUser current=FirebaseAuth.getInstance().getCurrentUser();
                if(p.getBoolean("enabled",false) && epoch.equals(p.getString("epoch",""))
                        && current!=null && account.equals(current.getUid())) {
                    p.edit().putString("binding",reply.getString("binding")).putBoolean("registration_error",false)
                        .putBoolean("preferences_pending",false).remove("registration_error_message").commit();
                } else {
                    // A logout during registration must not revive delivery on the server.
                    new ApiClient(origin,BuildConfig.DEBUG).request(auth,"POST","/v1/installations/"+id+"/unregister",
                        new JSONObject().put("secret",secret).put("binding",reply.getString("binding")));
                }
            }
            return Result.success();
        } catch(Exception failure) {
            synchronized(PushManager.class) {
                FirebaseUser current=FirebaseAuth.getInstance().getCurrentUser();
                if(!p.getBoolean("enabled",false) || !epoch.equals(p.getString("epoch",""))
                        || current==null || !account.equals(current.getUid())) return Result.success();
                p.edit().putBoolean("registration_error",true)
                    .putString("registration_error_message",ApiErrorMessages.describe(failure)).commit();
            }
            if(failure instanceof ApiClient.Failure) {
                int status=((ApiClient.Failure)failure).status;
                if(status>=400 && status<500 && status!=429) return Result.failure();
            }
            return getRunAttemptCount()<5 ? Result.retry() : Result.failure();
        }
    }
}
