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
            String id=data.get("message_id");
            Set<String> seen=new HashSet<>(p.getStringSet("seen",Collections.emptySet()));
            if(!PushPolicy.accepts(p.getBoolean("enabled",false),user==null ? null : user.getUid(),
                    p.getString("binding",""),data,seen)) return;
            // A 0.7 server adds alert_category/level; an older one only sends the legacy category.
            boolean test="test".equals(data.get("kind"));
            String category=AlertLevels.incomingCategory(data.get("alert_category"),data.get("category"));
            String local=AlertLevels.configurable(category) ? PushManager.level(p,category) : AlertLevels.ALERT;
            if(!AlertLevels.display(category,local,test)) return;
            if(seen.size()>=100) seen.clear(); seen.add(id);
            p.edit().putStringSet("seen",seen).putLong("last_received",System.currentTimeMillis()).commit();
            PushManager.channel(this);
            NotificationManager manager=getSystemService(NotificationManager.class);
            if(!manager.areNotificationsEnabled()) return;
            Intent open=new Intent(this,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP);
            PendingIntent intent=PendingIntent.getActivity(this,0,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
            String level=test ? AlertLevels.ALERT : local;
            String channel=AlertLevels.channel(category,level,PushManager.inQuietHours(p,Calendar.getInstance()));
            String title=AlertLevels.title(category), body=AlertLevels.body(category,test), group=AlertLevels.group(category);
            Notification notification=new Notification.Builder(this,channel)
                .setSmallIcon(android.R.drawable.ic_dialog_info).setContentTitle(title).setContentText(body).setGroup(group)
                .setContentIntent(intent).setAutoCancel(true).setVisibility(Notification.VISIBILITY_PRIVATE).build();
            // The silent summary keeps one stack per category; only the child decides sound and vibration.
            Notification summary=new Notification.Builder(this,channel)
                .setSmallIcon(android.R.drawable.ic_dialog_info).setContentTitle(title).setContentText(body).setGroup(group)
                .setGroupSummary(true).setGroupAlertBehavior(Notification.GROUP_ALERT_CHILDREN)
                .setContentIntent(intent).setAutoCancel(true).setVisibility(Notification.VISIBILITY_PRIVATE).build();
            try {
                manager.notify(AlertLevels.notificationId(id),notification);
                manager.notify(AlertLevels.summaryId(category),summary);
            } catch(SecurityException ignored) { /* permission revoked while receiving */ }
        }
    }
}
