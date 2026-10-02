package com.aircon.family;

import android.content.Context;
import android.content.Intent;
import android.os.Bundle;
import android.util.Base64;
import androidx.test.platform.app.InstrumentationRegistry;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseUser;
import com.google.android.gms.tasks.Tasks;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.concurrent.TimeUnit;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import static org.junit.Assert.*;

/** Only the signed-in owner can claim a provisioned hub through the existing public API. */
public class OwnHubSmokeTest extends OwnFamilySmokeTest {
    private ApiClient api;
    private String auth, homeId;

    private void owner() throws Exception {
        await("새 집 만들기");
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        android.content.SharedPreferences prefs=PushManager.prefs(context);
        FirebaseUser user=FirebaseAuth.getInstance().getCurrentUser();
        assertNotNull("Existing Google login required",user);
        assertTrue("Previously registered real notifications required",prefs.getBoolean("enabled",false));
        assertTrue("Own notification account must match current login",
            prefs.getString("account","").equals(user.getUid()));
        // Normal Firebase SDK authentication; credentials stay inside the phone.
        auth=Tasks.await(user.getIdToken(false),20,TimeUnit.SECONDS).getToken();
        api=new ApiClient(prefs.getString("origin",""),false);
        String name=new String(Base64.decode(InstrumentationRegistry.getArguments()
            .getString("home_name_b64",""),Base64.DEFAULT),StandardCharsets.UTF_8);
        assertFalse("Explicit user-approved home required",name.isEmpty());
        JSONArray homes=api.request(auth,"GET","/v1/me",null).getJSONArray("homes");
        for(int i=0;i<homes.length();i++) {
            JSONObject home=homes.getJSONObject(i);
            if(name.equals(home.optString("name")) && "owner".equals(home.optString("role"))) {
                assertNull("Approved home must be unique",homeId);
                homeId=home.getString("id");
            }
        }
        assertNotNull("Signed-in owner must own the approved home",homeId);
    }

    @Test public void verifyOwnerBeforeProvisioning() throws Exception {
        owner();
        assertEquals("Don't replace an already linked hub",0,
            api.request(auth,"GET","/v1/homes/"+homeId+"/hubs",null).getJSONArray("hubs").length());
        Bundle status=new Bundle();
        status.putString("hub_owner_preflight","existing_Google_owner_and_empty_approved_home_verified_no_credentials_exported");
        InstrumentationRegistry.getInstrumentation().sendStatus(0,status);
    }

    @Test public void claimApprovedHub() throws Exception {
        owner();
        File privateInput=new File(InstrumentationRegistry.getInstrumentation().getTargetContext()
            .getExternalFilesDir("pairing"),"approved-hub-claim.json");
        assertTrue("Explicit private pairing input required",privateInput.isFile());
        JSONObject claim;
        try {
            claim=new JSONObject(new String(Files.readAllBytes(privateInput.toPath()),StandardCharsets.UTF_8));
        } finally {
            assertTrue("One-use claim file must be removed",privateInput.delete());
        }
        assertEquals("Don't replace a linked hub",0,
            api.request(auth,"GET","/v1/homes/"+homeId+"/hubs",null).getJSONArray("hubs").length());
        JSONObject result=api.request(auth,"POST","/v1/homes/"+homeId+"/hubs/claim",
            new JSONObject().put("claim_code",claim.getString("claim_code")));
        assertTrue("Exact provisioned hub required",claim.getString("hub_id").equals(result.getString("id")));
        assertTrue("Exact approved owner's home required",homeId.equals(result.getString("home_id")));
        JSONArray hubs=api.request(auth,"GET","/v1/homes/"+homeId+"/hubs",null).getJSONArray("hubs");
        assertEquals(1,hubs.length());
        assertTrue(claim.getString("hub_id").equals(hubs.getJSONObject(0).getString("id")));
        Bundle status=new Bundle();
        status.putString("hub_claim","one_time_claim_consumed_by_existing_Google_owner_exact_hub_and_home_verified");
        InstrumentationRegistry.getInstrumentation().sendStatus(0,status);
        // No hub key or Google token is written to the test result, screenshots or laptop.
    }

    @Test public void observeActualHubFCM() throws Exception {
        owner();
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        android.content.SharedPreferences prefs=PushManager.prefs(context);
        long before=prefs.getLong("last_received",0);
        ownShell("input keyevent 3");ownShell("input keyevent 223");
        android.os.PowerManager power=context.getSystemService(android.os.PowerManager.class);
        long offDeadline=System.currentTimeMillis()+5000;
        while(power.isInteractive() && System.currentTimeMillis()<offDeadline) Thread.sleep(100);
        assertFalse("Display must be off before Pi event",power.isInteractive());
        Bundle waiting=new Bundle();waiting.putString("hub_receipt_wait","ready_for_real_pi_connection_event");
        InstrumentationRegistry.getInstrumentation().sendStatus(0,waiting);
        long deadline=System.currentTimeMillis()+90000;
        boolean notified=false;
        while(System.currentTimeMillis()<deadline) {
            for(android.service.notification.StatusBarNotification notice:
                    context.getSystemService(android.app.NotificationManager.class).getActiveNotifications()) {
                if(notice.getId()==10 && "새 기록이 도착했어요. 앱에서 확인해 주세요."
                        .contentEquals(notice.getNotification().extras.getCharSequence("android.text","")))
                    notified=true;
            }
            if(notified && prefs.getLong("last_received",0)>before) break;
            Thread.sleep(300);
        }
        assertTrue("New actual FCM callback and own posted event notification required",
            notified && prefs.getLong("last_received",0)>before);
        assertFalse("Display must remain off until Pi receipt",power.isInteractive());
        JSONArray events=api.request(auth,"GET","/v1/homes/"+homeId+"/events",null).getJSONArray("events");
        boolean connection=false;
        for(int i=0;i<events.length();i++)
            if("hub.connection_test".equals(events.getJSONObject(i).optString("kind"))) connection=true;
        assertTrue("Real Pi connection event must appear in the approved home",connection);
        Bundle received=new Bundle();received.putString("hub_fcm_receipt",
            "real_Pi_connection_record_and_new_FCM_callback_and_own_notification_verified");
        InstrumentationRegistry.getInstrumentation().sendStatus(0,received);
        ownShell("input keyevent 224");
        context.startActivity(new Intent(context,MainActivity.class)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP));
        await("새 집 만들기");click("알림 설정");await("최근 알림 수신 완료");
        InstrumentationRegistry.getInstrumentation().waitForIdleSync();Thread.sleep(350);
        screenshot("13-a50-pi-connection-fcm-receipt");
    }

    private void ownShell(String command) throws Exception {
        try(android.os.ParcelFileDescriptor output=automation.executeShellCommand(command)) {
            try(java.io.InputStream in=new android.os.ParcelFileDescriptor.AutoCloseInputStream(output)) {
                while(in.read()!=-1){}
            }
        }
    }
}
