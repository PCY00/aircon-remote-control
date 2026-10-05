package com.aircon.a50manager;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Configuration requires a caller holding the system settings permission. */
public final class ConfigurationReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context, Intent intent) {
        if (!"com.aircon.a50manager.CONFIGURE_TRUSTED_WIFI".equals(intent.getAction())) return;
        String network = intent.getStringExtra("network");
        if (network == null || network.length() == 0 || network.length() > 32) return;
        String bssid=intent.getStringExtra("bssid");
        if (bssid == null || !bssid.matches("(?i)[0-9a-f]{2}(:[0-9a-f]{2}){5}")) return;
        context.getSharedPreferences("recovery", Context.MODE_PRIVATE).edit()
            .putString("approved_network", network)
            .putString("approved_bssid",bssid.toLowerCase(java.util.Locale.ROOT))
            .putString("approved_dialog_title",intent.getStringExtra("dialog_title"))
            .putBoolean("auto_confirm_enabled", intent.getBooleanExtra("auto_confirm",true)).apply();
        String token=intent.getStringExtra("token");
        if (token != null && token.length() >= 32 && token.length() <= 128) {
            context.getSharedPreferences("recovery",Context.MODE_PRIVATE).edit()
                .putString("recovery_token",token).apply();
        }
        setResultCode(1);
    }
}
