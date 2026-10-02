package com.aircon.family;

import android.app.NotificationManager;
import android.os.ParcelFileDescriptor;
import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.util.Base64;
import android.view.accessibility.AccessibilityNodeInfo;
import androidx.test.platform.app.InstrumentationRegistry;
import java.nio.charset.StandardCharsets;
import org.junit.Test;
import static org.junit.Assert.*;

/** Operates signed production UI and checks only this app's receipt/notification state. */
public class OwnPushSmokeTest extends OwnFamilySmokeTest {
    @Test public void registerRealInstallation() throws Exception {
        await("새 집 만들기");click("알림 설정");await("알림 설정");click("이 휴대폰 알림 켜기");
        long deadline=System.currentTimeMillis()+60000;
        while(find("알림 연결됨")==null && System.currentTimeMillis()<deadline) {
            Thread.sleep(700);click("알림 연결 확인");
        }
        await("알림 연결됨");screenshot("10-a50-fcm-installation-registered");
        Bundle result=new Bundle();result.putString("push_registration","real_fcm_token_registered_no_token_export");
        InstrumentationRegistry.getInstrumentation().sendStatus(0,result);
    }
    @Test public void receiveRealFCMWhileBackgrounded() throws Exception {
        Context c=InstrumentationRegistry.getInstrumentation().getTargetContext();
        String encoded=InstrumentationRegistry.getArguments().getString("home_name_b64","");
        String home=new String(Base64.decode(encoded,Base64.DEFAULT),StandardCharsets.UTF_8);
        await("새 집 만들기");AccessibilityNodeInfo card=await(home).getParent();
        AccessibilityNodeInfo open=null;
        for(AccessibilityNodeInfo n:nodes(card)) if("집 열기".contentEquals(n.getText()==null?"":n.getText())) open=n;
        assertNotNull(open);assertTrue(open.performAction(AccessibilityNodeInfo.ACTION_CLICK));
        await(home);await("소유자 · 우리 가족의 스마트홈");
        long before=PushManager.prefs(c).getLong("last_received",0);
        click("이 휴대폰에 시험 알림 보내기");
        try(ParcelFileDescriptor output=automation.executeShellCommand("input keyevent 3")) {
            try(java.io.InputStream in=new ParcelFileDescriptor.AutoCloseInputStream(output)) { while(in.read()!=-1){} }
        }
        Thread.sleep(300);
        assertFalse("Client must be backgrounded before receipt",activity.getActivity().hasWindowFocus());
        long backgroundAt=System.currentTimeMillis();
        long deadline=System.currentTimeMillis()+60000;
        boolean posted=false;
        while(System.currentTimeMillis()<deadline) {
            for(android.service.notification.StatusBarNotification n:c.getSystemService(NotificationManager.class).getActiveNotifications())
                if(n.getId()==10 && "시험 알림이 도착했어요.".contentEquals(n.getNotification().extras.getCharSequence("android.text",""))) posted=true;
            if(posted && PushManager.prefs(c).getLong("last_received",0)>before
                    && PushManager.prefs(c).getLong("last_received",0)>=backgroundAt) break;
            Thread.sleep(300);
        }
        assertTrue("Real FCM callback after backgrounding and posted test notification required",posted
            && PushManager.prefs(c).getLong("last_received",0)>before && PushManager.prefs(c).getLong("last_received",0)>=backgroundAt);
        Bundle result=new Bundle();result.putString("fcm_receipt","real_data_message_callback_and_own_notification_posted_in_background");
        InstrumentationRegistry.getInstrumentation().sendStatus(0,result);
        c.startActivity(new Intent(c,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP));
        await("새 집 만들기");click("알림 설정");await("최근 알림 수신 완료");
        screenshot("11-a50-fcm-background-receipt");
    }
}
