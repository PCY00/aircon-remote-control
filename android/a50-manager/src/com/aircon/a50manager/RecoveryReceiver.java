package com.aircon.a50manager;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

/** The verified SSH client can request the same narrow recovery without launching an Activity. */
public final class RecoveryReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        if (!"com.aircon.a50manager.RECOVER".equals(intent.getAction())) return;
        SharedPreferences preferences=context.getSharedPreferences("recovery",Context.MODE_PRIVATE);
        String expected=preferences.getString("recovery_token","");
        String supplied=intent.getStringExtra("token");
        if (expected.length() < 32 || !expected.equals(supplied) || !Maintenance.enabled(context)) {
            setResultCode(0); setResultData("RECOVERY_REQUEST_REJECTED"); return;
        }
        String result=Maintenance.restore(context);
        TrustedWifiApproval.requestInspection();
        setResultCode(1); setResultData(result);
    }
}
