package com.aircon.a50manager;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.provider.Settings;

/** Read-only non-secret diagnostics for the SSH management path. */
public final class StatusReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        if (!"com.aircon.a50manager.STATUS".equals(intent.getAction())) return;
        SharedPreferences state=context.getSharedPreferences("recovery",Context.MODE_PRIVATE);
        setResultCode(0);
        setResultData("enabled="+Maintenance.enabled(context)
            + ";permission="+Maintenance.permissionGranted(context)
            + ";wifi_adb="+Settings.Global.getInt(context.getContentResolver(),"adb_wifi_enabled",0)
            + ";approval="+state.getBoolean("auto_confirm_enabled",false)
            + ";approval_state="+state.getString("approval_state","NO_DIALOG_OBSERVED")
            + ";service_connected="+TrustedWifiApproval.isConnected()
            + ";inspection_count="+TrustedWifiApproval.inspectionCount()
            + ";last_approval="+state.getString("last_approval","NONE")
            + ";interactive="+context.getSystemService(android.os.PowerManager.class).isInteractive()
            + ";last="+state.getString("last_result",""));
    }
}
