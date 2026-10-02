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
    @Test public void verifyNotificationGuidanceAndChoices() throws Exception {
        Context c=InstrumentationRegistry.getInstrumentation().getTargetContext();
        android.content.SharedPreferences prefs=PushManager.prefs(c);
        boolean enabled=prefs.getBoolean("enabled",false);
        String home=new String(Base64.decode(InstrumentationRegistry.getArguments()
            .getString("home_name_b64",""),Base64.DEFAULT),StandardCharsets.UTF_8);
        await("새 집 만들기");
        try {
            // Reproduce only this client's off state; no unregister, account or server change.
            prefs.edit().putBoolean("enabled",false).commit();
            openHome(home);click("이 휴대폰에 시험 알림 보내기");
            await("이 휴대폰 알림을 켜주세요");
            screenshot("14-a50-notification-off-guidance");click("닫기");
            prefs.edit().putBoolean("enabled",enabled).commit();
            click("받을 알림 선택");await("알림 설정");await("받고 싶은 알림");
            assertNotNull(find("문 열림·닫힘"));assertNotNull(find("온습도 측정"));
            assertNotNull(find("자동화 경고 발생·해제"));
            screenshot("15-a50-notification-choices");
            click("집 목록으로");await("새 집 만들기");openHome(home);
            click("이 집 삭제");await("이 집을 삭제할까요?");
            AccessibilityNodeInfo input=null;
            for(AccessibilityNodeInfo n:nodes(automation.getRootInActiveWindow()))
                if("android.widget.EditText".contentEquals(n.getClassName())) input=n;
            assertNotNull(input);Bundle value=new Bundle();value.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,"wrong-confirmation");
            assertTrue(input.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,value));click("집 삭제");
            Thread.sleep(300);assertNotNull("Wrong name must keep deletion confirmation open",find("이 집을 삭제할까요?"));
            screenshot("16-a50-home-delete-confirmation");click("취소");
            await(home);await("소유자 · 우리 가족의 스마트홈");
            Bundle result=new Bundle();result.putString("notification_guidance","off_state_guidance_choices_and_wrong_name_delete_guard_passed_no_server_deletion");
            InstrumentationRegistry.getInstrumentation().sendStatus(0,result);
        } finally {
            prefs.edit().putBoolean("enabled",enabled).commit();
        }
    }
    private void openHome(String name) throws Exception {
        AccessibilityNodeInfo card=await(name).getParent();AccessibilityNodeInfo open=null;
        for(AccessibilityNodeInfo n:nodes(card)) if("집 열기".contentEquals(n.getText()==null?"":n.getText())) open=n;
        assertNotNull(open);assertTrue(open.performAction(AccessibilityNodeInfo.ACTION_CLICK));
        await(name);await("소유자 · 우리 가족의 스마트홈");
    }
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
        com.google.firebase.auth.FirebaseUser user=com.google.firebase.auth.FirebaseAuth.getInstance().getCurrentUser();
        assertNotNull(user);
        String auth=com.google.android.gms.tasks.Tasks.await(user.getIdToken(false),20,java.util.concurrent.TimeUnit.SECONDS).getToken();
        ApiClient api=new ApiClient(PushManager.prefs(c).getString("origin",""),false);
        org.json.JSONArray homes=api.request(auth,"GET","/v1/me",null).getJSONArray("homes");
        String homeId=null;
        for(int index=0;index<homes.length();index++) {
            org.json.JSONObject item=homes.getJSONObject(index);
            if(home.equals(item.optString("name")) && "owner".equals(item.optString("role"))) {
                assertNull(homeId);homeId=item.getString("id");
            }
        }
        assertNotNull(homeId);
        long before=PushManager.prefs(c).getLong("last_received",0);
        try(ParcelFileDescriptor output=automation.executeShellCommand("input keyevent 3")) {
            try(java.io.InputStream in=new ParcelFileDescriptor.AutoCloseInputStream(output)) { while(in.read()!=-1){} }
        }
        Thread.sleep(300);
        assertFalse("Client must be backgrounded before receipt",activity.getActivity().hasWindowFocus());
        long backgroundAt=System.currentTimeMillis();
        // Trigger only after backgrounding: a fast callback must not race the Home transition.
        org.json.JSONObject queued=api.request(auth,"POST","/v1/homes/"+homeId+"/notifications/test",
            new org.json.JSONObject().put("installation_id",PushManager.installation(c)));
        assertEquals("queued",queued.getString("status"));assertEquals(1,queued.getInt("queued"));
        long deadline=System.currentTimeMillis()+60000;
        boolean posted=false;
        while(System.currentTimeMillis()<deadline) {
            for(android.service.notification.StatusBarNotification n:c.getSystemService(NotificationManager.class).getActiveNotifications())
                if(n.getId()==10 && "시험 알림이 도착했어요.".contentEquals(n.getNotification().extras.getCharSequence("android.text",""))) posted=true;
            if(posted && PushManager.prefs(c).getLong("last_received",0)>before
                    && PushManager.prefs(c).getLong("last_received",0)>=backgroundAt) break;
            Thread.sleep(300);
        }
        Bundle timing=new Bundle();
        timing.putString("receipt_diagnostic","posted="+posted+";new_callback="+(PushManager.prefs(c).getLong("last_received",0)>before)
            +";callback_after_background="+(PushManager.prefs(c).getLong("last_received",0)>=backgroundAt));
        InstrumentationRegistry.getInstrumentation().sendStatus(0,timing);
        assertTrue("Real FCM callback after backgrounding and posted test notification required",posted
            && PushManager.prefs(c).getLong("last_received",0)>before && PushManager.prefs(c).getLong("last_received",0)>=backgroundAt);
        Bundle result=new Bundle();result.putString("fcm_receipt","real_data_message_callback_and_own_notification_posted_in_background");
        InstrumentationRegistry.getInstrumentation().sendStatus(0,result);
        c.startActivity(new Intent(c,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP));
        await("새 집 만들기");click("알림 설정");await("최근 알림 수신 완료");
        InstrumentationRegistry.getInstrumentation().waitForIdleSync();
        Thread.sleep(350);
        await("최근 알림 수신 완료");
        screenshot("11-a50-fcm-background-receipt");
    }

    @Test public void receiveRealFCMWhileScreenOff() throws Exception {
        Context c=InstrumentationRegistry.getInstrumentation().getTargetContext();
        await("새 집 만들기");
        android.content.SharedPreferences prefs=PushManager.prefs(c);
        assertTrue("Explicit notification registration is required",prefs.getBoolean("enabled",false));
        com.google.firebase.auth.FirebaseUser user=com.google.firebase.auth.FirebaseAuth.getInstance().getCurrentUser();
        assertNotNull(user);
        assertEquals(prefs.getString("account",""),user.getUid());
        // Use the same SDK and authenticated API as the app. No credentials leave the phone.
        String auth=com.google.android.gms.tasks.Tasks.await(user.getIdToken(false),20,
            java.util.concurrent.TimeUnit.SECONDS).getToken();
        ApiClient api=new ApiClient(prefs.getString("origin",""),false);
        String homeName=new String(Base64.decode(InstrumentationRegistry.getArguments()
            .getString("home_name_b64",""),Base64.DEFAULT),StandardCharsets.UTF_8);
        org.json.JSONArray homes=api.request(auth,"GET","/v1/me",null).getJSONArray("homes");
        String homeId=null;
        for(int index=0;index<homes.length();index++) {
            org.json.JSONObject home=homes.getJSONObject(index);
            if(homeName.equals(home.optString("name")) && "owner".equals(home.optString("role"))) {
                assertNull("The approved test home must be unique",homeId);
                homeId=home.getString("id");
            }
        }
        assertNotNull("The signed-in owner must have the approved home",homeId);
        long before=prefs.getLong("last_received",0);
        ownShell("input keyevent 3");
        ownShell("input keyevent 223");
        android.os.PowerManager power=c.getSystemService(android.os.PowerManager.class);
        long offDeadline=System.currentTimeMillis()+5000;
        while(power.isInteractive() && System.currentTimeMillis()<offDeadline) Thread.sleep(100);
        assertFalse("Display must be off before the request",power.isInteractive());
        assertFalse("Client must be backgrounded",activity.getActivity().hasWindowFocus());
        long screenOffAt=System.currentTimeMillis();
        org.json.JSONObject queued=api.request(auth,"POST","/v1/homes/"+homeId+"/notifications/test",
            new org.json.JSONObject().put("installation_id",PushManager.installation(c)));
        assertEquals("queued",queued.getString("status"));assertEquals(1,queued.getInt("queued"));
        long deadline=System.currentTimeMillis()+60000;
        boolean posted=false;
        while(System.currentTimeMillis()<deadline) {
            for(android.service.notification.StatusBarNotification n:c.getSystemService(NotificationManager.class).getActiveNotifications())
                if(n.getId()==10 && "시험 알림이 도착했어요.".contentEquals(n.getNotification().extras.getCharSequence("android.text",""))) posted=true;
            if(posted && prefs.getLong("last_received",0)>before && prefs.getLong("last_received",0)>=screenOffAt) break;
            Thread.sleep(300);
        }
        assertTrue("New real callback and posted notification required",posted
            && prefs.getLong("last_received",0)>before && prefs.getLong("last_received",0)>=screenOffAt);
        assertFalse("Display must remain off until receipt",power.isInteractive());
        Bundle result=new Bundle();result.putString("fcm_receipt",
            "real_data_message_callback_and_own_notification_posted_while_display_noninteractive");
        result.putString("test_send","same_owner_API_requested_after_display_off_no_token_export");
        InstrumentationRegistry.getInstrumentation().sendStatus(0,result);
        ownShell("input keyevent 224");
        c.startActivity(new Intent(c,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP));
        await("새 집 만들기");click("알림 설정");await("최근 알림 수신 완료");
        InstrumentationRegistry.getInstrumentation().waitForIdleSync();Thread.sleep(350);
        await("최근 알림 수신 완료");screenshot("12-a50-fcm-screen-off-receipt");
    }

    private void ownShell(String command) throws Exception {
        try(ParcelFileDescriptor output=automation.executeShellCommand(command)) {
            try(java.io.InputStream in=new ParcelFileDescriptor.AutoCloseInputStream(output)) {
                while(in.read()!=-1){}
            }
        }
    }
}
