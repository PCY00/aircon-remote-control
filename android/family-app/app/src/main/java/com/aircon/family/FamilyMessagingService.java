package com.aircon.family;

import android.app.*;
import android.content.Intent;
import android.content.SharedPreferences;
import com.google.firebase.auth.*;
import com.google.firebase.messaging.*;
import java.util.*;

public final class FamilyMessagingService extends FirebaseMessagingService {
    @Override public void onNewToken(String token) {
        synchronized(PushManager.class) { PushManager.prefs(this).edit().remove("binding").putString("epoch",UUID.randomUUID().toString()).commit(); }
        PushManager.sync(this);
    } // never log tokens
    @Override public void onMessageReceived(RemoteMessage message) {
        if(!BuildConfig.FLAVOR.equals("production")) return;
        synchronized(PushManager.class) {
            SharedPreferences p=PushManager.prefs(this); Map<String,String> data=message.getData();
            FirebaseUser user=FirebaseAuth.getInstance().getCurrentUser();
            String id=data.get("message_id"),binding=data.get("binding");
            Set<String> seen=new HashSet<>(p.getStringSet("seen",Collections.emptySet()));
            if(!PushPolicy.accepts(p.getBoolean("enabled",false),user==null ? null : user.getUid(),
                    p.getString("binding",""),data,seen)) return;
            if(seen.size()>=100) seen.clear(); seen.add(id);
            p.edit().putStringSet("seen",seen).putLong("last_received",System.currentTimeMillis()).commit();
            PushManager.channel(this);
            NotificationManager manager=getSystemService(NotificationManager.class);
            if(!manager.areNotificationsEnabled()) return;
            Intent open=new Intent(this,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP);
            PendingIntent intent=PendingIntent.getActivity(this,0,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
            Notification notification=new Notification.Builder(this,PushManager.CHANNEL)
                .setSmallIcon(android.R.drawable.ic_dialog_info).setContentTitle("우리 집 알림")
                .setContentText("test".equals(data.get("kind")) ? "시험 알림이 도착했어요." : "새 기록이 도착했어요. 앱에서 확인해 주세요.")
                .setContentIntent(intent).setAutoCancel(true).setVisibility(Notification.VISIBILITY_PRIVATE).build();
            try { manager.notify(10,notification); } catch(SecurityException ignored) { /* permission revoked while receiving */ }
        }
    }
}
