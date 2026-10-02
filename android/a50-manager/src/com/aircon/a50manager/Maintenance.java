package com.aircon.a50manager;

import android.Manifest;
import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.content.Context;
import android.content.pm.PackageManager;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import android.os.PowerManager;
import android.provider.Settings;
import android.util.Log;

final class Maintenance {
    private static final int JOB_ID = 505;
    static boolean enabled(Context context) {
        return context.getSharedPreferences("recovery", Context.MODE_PRIVATE)
            .getBoolean("enabled", true);
    }
    static void setEnabled(Context context, boolean value) {
        context.getSharedPreferences("recovery", Context.MODE_PRIVATE).edit()
            .putBoolean("enabled", value).apply();
        schedule(context);
    }
    static boolean permissionGranted(Context context) {
        return context.checkSelfPermission(Manifest.permission.WRITE_SECURE_SETTINGS)
            == PackageManager.PERMISSION_GRANTED;
    }
    static String restore(Context context) {
        String result;
        if (!enabled(context)) result = "자동 복구 꺼짐";
        else if (!permissionGranted(context)) result = "최초 관리 권한 설정 필요";
        else {
            ConnectivityManager network = context.getSystemService(ConnectivityManager.class);
            NetworkCapabilities capabilities = network.getNetworkCapabilities(network.getActiveNetwork());
            if (capabilities == null || !capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)) {
                result = "Wi-Fi 연결 대기";
            } else {
                try {
                    // Only this setting is ever modified; system network trust checks stay active.
                    if (Settings.Global.getInt(context.getContentResolver(), "adb_wifi_enabled", 0) == 0) {
                        // Android 11: briefly wake the screen so the configured dialog service can see it.
                        // This expires automatically; no permanent display wake lock is retained.
                        if (context.getSharedPreferences("recovery", Context.MODE_PRIVATE)
                            .getBoolean("auto_confirm_enabled", false)) {
                            PowerManager power=context.getSystemService(PowerManager.class);
                            PowerManager.WakeLock wake=power.newWakeLock(
                                PowerManager.SCREEN_DIM_WAKE_LOCK | PowerManager.ACQUIRE_CAUSES_WAKEUP,
                                "A50Recovery:debug-dialog");
                            wake.acquire(15000L);
                        }
                        boolean written = Settings.Global.putInt(context.getContentResolver(), "adb_wifi_enabled", 1);
                        result = written ? "무선 디버깅 복구 요청 완료" : "설정 저장 실패";
                    } else result = "무선 디버깅 유지 중";
                } catch (SecurityException error) {
                    result = "설정 복구 권한 없음";
                    Log.w("A50Recovery", result, error);
                }
            }
        }
        context.getSharedPreferences("recovery", Context.MODE_PRIVATE).edit()
            .putString("last_result", result).apply();
        Log.i("A50Recovery", result);
        return result;
    }
    static void schedule(Context context) {
        JobScheduler scheduler = context.getSystemService(JobScheduler.class);
        if (!enabled(context)) {
            scheduler.cancel(JOB_ID);
            return;
        }
        JobInfo job = new JobInfo.Builder(JOB_ID, new ComponentName(context, RecoveryJob.class))
            .setPeriodic(15 * 60 * 1000L)
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
            .setPersisted(true)
            .build();
        if (scheduler.schedule(job) != JobScheduler.RESULT_SUCCESS) {
            Log.w("A50Recovery", "보조 복구 작업 예약 실패");
        }
    }
}
